import os
import logging
import pytest
from colorama import init, Fore, Style
from _pytest.reports import TestReport
import sys
import re
import shutil
from typing import Dict, Tuple, Optional
from tac.core.llm import LLMClient, Message
from tac.blocks import ProtoBlock
from tac.utils.project_files import ProjectFiles
from tac.core.config import config
from tac.core.log_config import setup_logging
from tac.trusty_agents.base import TrustyAgent

logger = setup_logging('tac.trusty_agents.pytest')


class ErrorAnalyzer:
    """Analyzes test failures and implementation errors to provide insights using LLM"""
    
    def __init__(self):
        logger.info("Initializing ErrorAnalyzer")
        self.llm_client = LLMClient(strength="strong")
        self.project_files = ProjectFiles()



    def analyze_failure(self, protoblock: ProtoBlock, test_results: str, codebase: Dict[str, str]) -> str:
        """
        Analyzes test failures and implementation errors using LLM.
        
        Args:
            protoblock: The ProtoBlock that failed
            test_results: The test results/error output
            codebase: Dictionary mapping file paths to their contents or string content
            
        Returns:
            str: Detailed analysis of what went wrong and suggestions for improvement
        """
        logger.info("Starting LLM-based failure analysis")
        logger.debug(f"ProtoBlock ID: {protoblock.block_id}")
        logger.debug(f"Test results length: {len(test_results) if test_results else 'None'}")
        
        try:
            # Use centralized config
            use_summaries = config.general.use_file_summaries
            logger.info(f"Using file summaries: {use_summaries}")
            
            # Format codebase for prompt
            logger.info("Formatting codebase for LLM prompt")
            codebase_content = []
            
            # Handle string codebase
            if isinstance(codebase, str):
                codebase_content.append(f"Codebase Content:\n```python\n{codebase}\n```")
            else:
                # Handle dictionary codebase
                logger.debug(f"Codebase files to analyze: {list(codebase.keys())}")
                for path, content in codebase.items():
                    logger.debug(f"Processing file: {path}")
                    if use_summaries:
                        # Use existing summaries instead of generating new ones
                        summary = self.project_files._load_existing_summaries().get(path, {}).get('summary')
                        if summary:
                            file_content = f"File Summary:\n{summary}"
                        else:
                            file_content = content
                    else:
                        file_content = content
                    codebase_content.append(f"File: {path}\n```python\n{file_content}\n```")
            
            codebase_str = "\n\n".join(codebase_content)
            logger.debug(f"Formatted codebase length: {len(codebase_str)} characters")
            
            # Prepare prompt
            analysis_prompt = f"""<purpose>
You are a senior python software engineer analyzing a failed implementation attempt. Your goal is to provide a clear and detailed analysis of what went wrong and suggest specific improvements. The information for the junior software engineer who failed at their attempt is given in the <protoblock> section, the codebase in <codebase_str>, the test results in <test_results>. Your concrete analysis rules are given in <analysis_rules>.
</purpose>

<codebase_state>
{codebase_str}
</codebase_state>

<protoblock>
Task Description: {protoblock.task_description}
Test Specification: {protoblock.test_specification}
Test Data: {protoblock.test_data_generation}
Write Files: {protoblock.write_files}
Context Files: {protoblock.context_files}
</protoblock>

<test_results>
{test_results}
</test_results>

<analysis_rules>
1. First identify the type of failure (syntax error, runtime error, test assertion, etc.)
2. Gather understanding whether the error is due to an already existing test, that needs to be updated, because the protoblock makes it necessary to change existing tests.
3. In case the error is due to an already existing test, that needs to be updated, provide a detailed description of how to update the test.
4. In case the error is due to a missing file, list the files that need to be created.
5. In case the error is due to a missing import, list the imports that need to be added.
</analysis_rules>

<output_format>
Provide your analysis in the following structure:

NEW STRATEGY FOR SOLVING THE TASK:
(In more detail describe how the next implementation attempt should look like based on whst you learned from the previois attempt.)

MISSING WRITE FILES:
(so far it was possible to modify these files: {protoblock.write_files}. However, given youn analysis, do we need to edit more files? If there are files missing, directly mention them here in a list, without any additional text e.g. your reply is ["tests/test_piano_trainer_main.py"])
</output_format>"""

            messages = [
                Message(role="system", content="You are a coding assistant specialized in analyzing test failures and implementation errors. Provide clear, actionable analysis."),
                Message(role="user", content=analysis_prompt)
            ]
            
            response = self.llm_client.chat_completion(messages)
            
            if not response or not response.strip():
                logger.error("Received empty response from LLM")
                return "Error: Unable to generate analysis"
                
            return response
            
        except Exception as e:
            logger.error(f"Error during LLM failure analysis: {str(e)}", exc_info=True)
            return f"Error analyzing failure: {str(e)}" 

class CustomReporter:
    def __init__(self):
        self.test_functions = []
        self.results = {'passed': 0, 'failed': 0, 'error': 0, 'skipped': 0}
        self.output_lines = []
        
    def pytest_runtest_logreport(self, report: TestReport):
        if report.when == 'call' or (report.when == 'setup' and report.outcome == 'skipped'):
            self.test_functions.append(report.nodeid.split("::")[-1])
            if report.passed:
                self.results['passed'] += 1
            elif report.failed:
                self.results['failed'] += 1
            elif report.skipped:
                self.results['skipped'] += 1
        if hasattr(report, 'longrepr'):
            if report.longrepr:
                self.output_lines.append(str(report.longrepr))

class PytestTestingAgent(TrustyAgent):
    """
    A dedicated class for handling test execution and reporting using pytest.
    """
    def __init__(self):
        init()  # Initialize colorama
        self.test_results = ""
        self.test_functions = []
        self.had_execution_error = False
        self._test_stats = {'passed': 0, 'failed': 0, 'error': 0, 'skipped': 0}
        self.error_analyzer = ErrorAnalyzer()  # Initialize error analyzer
        

    def _check_impl(self, protoblock: ProtoBlock, codebase: Dict[str, str], code_diff: str) -> Tuple[bool, str, str]:
        """
        Run tests and check if they pass.
        
        Args:
            protoblock: The ProtoBlock containing task specifications
            codebase: Dictionary mapping file paths to their contents
            code_diff: The git diff showing implemented changes (not used in this agent)
            
        Returns:
            Tuple containing:
            - bool: Success status (True if tests passed, False otherwise)
            - str: Error analysis (empty string if success is True)
            - str: Failure type description (empty string if success is True)
        """
        try:
            test_path = config.general.test_path
            logger.info("Test Execution Details:")
            logger.info("="*50)
            logger.info(f"Test path: {test_path}")
            logger.info(f"Working directory: {os.getcwd()}")
            logger.info(f"Python path: {sys.path}")
            logger.info("="*50)
            
            test_success = self.run_tests(test_path)
            test_results = self.get_test_results()
        except Exception as e:
            error_msg = f"Error during test execution: {type(e).__name__}: {str(e)}"
            logger.error(error_msg)
            test_results = error_msg
            test_success = False

        
        # Extract test statistics
        test_stats = self.get_test_stats()
        total_tests = sum(test_stats.values()) if test_stats else 0
        failed_tests = test_stats.get('failed', 0) if test_stats else 0
        
        # Log test results
        if failed_tests > 0:
            logger.warning(f"{failed_tests} out of {total_tests} tests failed")
            logger.warning("This indicates potential issues but won't stop execution")
        else:
            logger.info(f"All {total_tests} tests passed successfully")

        # Only return early if tests failed
        if not test_success:
            failure_type = "Pytest failed"
            execution_success = False
            error_analysis = ""  # Initialize as empty string instead of "None"
            logger.debug(f"Software test result: NO SUCCESS. Test results: {test_results}")

            if config.general.run_error_analysis:
                error_analysis = self.error_analyzer.analyze_failure(
                    protoblock, 
                    test_results,
                    codebase
                )
                logger.debug(f"Error Analysis: {error_analysis}")
            else:
                logger.debug("Software test result: FAILURE!")

            logger.info("Returning early due to test failure, skipping any remaining trusty agents")
            return execution_success, error_analysis, failure_type
        else:
            return True, "", ""

    def get_test_stats(self) -> dict:
        """Get the current test statistics"""
        return self._test_stats.copy()

    def run_tests(self, test_path: str = None) -> bool:
        """
        Runs the tests using pytest framework.
        Args:
            test_path: Optional path to test file or directory. If None, runs all tests/test*.py files
        Returns:
            bool: True only if all tests passed successfully, False if there were any failures or execution errors
        """
        try:
            test_target = test_path or 'tests'
            full_path = test_target
            if os.path.exists('.pytest_cache'):
                shutil.rmtree('.pytest_cache')
                logger.debug("Removed pytest cache")
            else:
                logger.debug("Did not remove any pytest cache")

            if not os.path.exists(full_path):
                error_msg = f"Error: Test path not found: {full_path}"
                logger.error(error_msg)
                self.test_results = error_msg
                self.had_execution_error = True
                return False

            reporter = CustomReporter()
            plugins = [reporter]
            
            # Add current directory to Python path
            if os.getcwd() not in sys.path:
                sys.path.insert(0, os.getcwd())
            
            # Run pytest with captured output
            args = ['-v', '--disable-warnings']
            
            # If test_path is a file, use it directly
            # If it's a directory, use a pattern to find all test files
            if os.path.isfile(test_target):
                args.append(test_target)
            else:
                # Use a more explicit pattern to find all test files
                args.extend([test_target, '--collect-only'])
                # First collect all tests to ensure we're finding everything
                collection_exit_code = pytest.main(args, plugins=[])
                # Then run the actual tests
                args = ['-v', '--disable-warnings', '-m', 'not performance and not transient', test_target]
            
            exit_code = pytest.main(args, plugins=plugins)
            
            # Process results
            self.test_functions = reporter.test_functions
            self._test_stats = reporter.results
            self._print_test_summary(self._test_stats)
            
            # Store full output
            self.test_results = "\n".join(reporter.output_lines)
            if self.test_results:
                self.test_results += "\n\n"
            
            summary = self._generate_summary(self._test_stats, exit_code)
            self.test_results += summary
            
            # Log all test results to logger.debug
            logger.debug(f"Test Results:\n{self.test_results}")
            
            # Determine test success:
            # - exit_code 0: all tests passed
            # - exit_code 5: no tests found (considered ok)
            # - failed_tests == 0: no test failures
            execution_ok = exit_code in [0, 5]
            no_test_failures = self._test_stats['failed'] == 0
            test_success = execution_ok and no_test_failures
            
            # Update execution error state for other parts of the system
            self.had_execution_error = not execution_ok
            
            return test_success
            
        except Exception as e:
            error_msg = f"Error running tests: {type(e).__name__}: {str(e)}"
            logger.exception(error_msg)
            self.test_results = error_msg
            self.had_execution_error = True
            return False

    def _generate_summary(self, results: dict, exit_code: int) -> str:
        summary = "\nTest Summary:\n"
        if exit_code == 0:
            summary += "All tests passed!\n"
        elif exit_code == 5:
            summary += "No tests were found.\n"
            summary += "This is not a failure - it just means no tests exist yet.\n"
        else:
            summary += f"Tests failed with exit code {exit_code}\n"
        
        summary += f"Passed: {results['passed']}\n"
        if results['failed'] > 0:
            summary += f"Failed: {results['failed']}\n"
        if results['error'] > 0:
            summary += f"Errors: {results['error']}\n"
        if results['skipped'] > 0:
            summary += f"Skipped: {results['skipped']}\n"
        return summary

    def _print_test_summary(self, results: dict):
        """Print a colored summary of test results"""
        total = sum(results.values())
        color = Fore.RED if results['failed'] > 0 or results['error'] > 0 else Fore.GREEN
        
        logger.info("="*50)
        logger.info(f"{color}Test Summary:{Style.RESET_ALL}")
        
        if results['failed'] > 0 or results['error'] > 0:
            logger.info(f"{Fore.RED}Passed: {results['passed']}/{total}{Style.RESET_ALL}")
            if results['failed'] > 0:
                logger.info(f"{Fore.RED}Failed: {results['failed']}{Style.RESET_ALL}")
            if results['error'] > 0:
                logger.info(f"{Fore.RED}Errors: {results['error']}{Style.RESET_ALL}")
        else:
            logger.info(f"{Fore.GREEN}Passed: {results['passed']}/{total}{Style.RESET_ALL}")
        
        if results['skipped'] > 0:
            logger.info(f"{Fore.YELLOW}Skipped: {results['skipped']}{Style.RESET_ALL}")
        logger.info("="*50)

    def get_test_results(self) -> str:
        """Get the full test results including output and summary"""
        return self.test_results 

    def get_test_functions(self) -> list:
        """Get the list of collected test function names, extracting function names after '::' if present"""
        return [s.split("::")[-1].strip() if "::" in s else s for s in self.test_functions]

    def collect_all_tests(self, tests_dir: str = "tests") -> list:
        """Recursively scan the specified tests directory to collect all test function names"""
        test_names = []
        for root, dirs, files in os.walk(tests_dir):
            for file in files:
                if file.endswith(".py") and (file.startswith("test_") or file.endswith("_test.py")):
                    filepath = os.path.join(root, file)
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            content = f.read()
                            test_names.extend(re.findall(r"def (test_[a-zA-Z0-9_]+)\(", content))
                    except Exception as e:
                        logger.error(f"Failed to read file {filepath}: {e}")
        return test_names

    def get_modified_tests(self, baseline: float, tests_dir: str = "tests") -> list:
        """Determine which test functions have been modified since the given baseline timestamp"""
        modified_tests = []
        for root, dirs, files in os.walk(tests_dir):
            for file in files:
                if file.endswith(".py") and (file.startswith("test_") or file.endswith("_test.py")):
                    filepath = os.path.join(root, file)
                    try:
                        mtime = os.path.getmtime(filepath)
                        if mtime > baseline:
                            with open(filepath, "r", encoding="utf-8") as f:
                                content = f.read()
                                modified_tests.extend(re.findall(r"def (test_[a-zA-Z0-9_]+)\(", content))
                    except Exception as e:
                        logger.error(f"Failed to process file {filepath}: {e}")
        return modified_tests

