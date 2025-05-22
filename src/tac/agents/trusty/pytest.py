import os
import logging
import pytest
from colorama import init, Fore, Style
from _pytest.reports import TestReport
import sys
import re
import shutil
from typing import Dict, Tuple, Optional, Union
from tac.core.llm import LLMClient, Message
from tac.blocks import ProtoBlock
from tac.utils.project_files import ProjectFiles
from tac.core.config import config
from tac.core.log_config import setup_logging
from tac.agents.trusty.base import TrustyAgent, trusty_agent
from tac.agents.trusty.results import TrustyAgentResult
import glob

logger = setup_logging('tac.trusty_agents.pytest')

@trusty_agent(
    name="pytest",
    description="ONLY use for python code updates. Do not use for threejs or html. Use this agent to create and runs new unit tests for PYTHON code using pytest. Use it to verify isolated functionality and test of small scale functions. Do not use for visual verifications or anything related to threejs, java, html, css, etc.",
    protoblock_prompt="Given the codebase and the instructions, here you describe the test outline. We are aiming to just write ONE single test ideally, which checks if the functionality update in the code has been implemented correctly. The goal is to ensure that the task instructions have been implemented correctly via an empirical test. Critically, the test needs to be fulfillable given the changes in the files we are making. We just need a test for the new task! It should be a test that realistically can be executed, be careful for instance with tests that would spawn UI and then everything blocks! However if we don't need a test, just skip this step and leave the field empty. If we alrady have a similar test in our codebase, we definitely want to write into the same test file and append the new test. Furthermore, describe in detail the input data for the test and the expected outcome. Use the provided codebase as a reference. The more detail the better, make it as concrete as possible. However if we don't need a test, just skip this step and leave the field empty. Be sure that you include or modify tests files, and add them to the write_files section, it should be of the pattern tests/test_<filename>.py",
    prompt_target = "coding_agent",
    llm="o3-mini",
    mandatory=True
)
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
        
    def should_run_mandatory(self, protoblock: ProtoBlock, codebase: Dict[str, str]) -> Tuple[bool, str]:
        """
        Check if pytest agent should run based on presence of Python test files.
        
        Args:
            protoblock: The ProtoBlock containing task specifications
            codebase: Dictionary mapping file paths to their contents
            
        Returns:
            Tuple containing:
            - bool: True if agent should run, False if it can be skipped
            - str: Reason for the decision (for logging)
        """
        test_path = config.general.test_path or 'tests'
        
        # First check if directory exists
        if not os.path.exists(test_path):
            return False, f"Test directory {test_path} does not exist"
        
        # Check for Python test files
        for root, _, files in os.walk(test_path):
            for file in files:
                if file.endswith('.py') and (file.startswith('test_') or file.endswith('_test.py')):
                    return True, f"Found Python test file: {os.path.join(root, file)}"
        
        return False, f"No Python test files found in {test_path}"

    def _check_impl(self, protoblock: ProtoBlock, codebase: Dict[str, str], code_diff: str) -> Union[Tuple[bool, str, str], TrustyAgentResult]:
        """
        Run tests and check if they pass.
        
        Args:
            protoblock: The ProtoBlock containing task specifications
            codebase: Dictionary mapping file paths to their contents
            code_diff: The git diff showing implemented changes (not used in this agent)
            
        Returns:
            TrustyAgentResult: Result object with test information
        """
        # Create a result object for this agent
        result = TrustyAgentResult(
            success=False,  # Default to False, will set to True if successful
            agent_type="pytest",
            summary="Running pytest tests"
        )
        
        try:
            test_path = config.general.test_path
            logger.info("Test Execution Details:")
            logger.info(f"Test path: {test_path}")
            logger.info(f"Working directory: {os.getcwd()}")
            logger.info(f"Python path: {sys.path}")
            
            # Add details to result
            result.details["test_path"] = test_path
            result.details["working_directory"] = os.getcwd()
            
            # Reload modules to ensure we're using the latest code
            self._reload_modules()
            
            test_success = self.run_tests(test_path)
            test_results = self.get_test_results()
            
            # Add test results to result object
            result.add_report(test_results, "Test Results")
            
            # Extract test statistics
            test_stats = self.get_test_stats()
            total_tests = sum(test_stats.values()) if test_stats else 0
            passed_tests = test_stats.get('passed', 0) if test_stats else 0
            failed_tests = test_stats.get('failed', 0) if test_stats else 0
            error_tests = test_stats.get('error', 0) if test_stats else 0
            skipped_tests = test_stats.get('skipped', 0) if test_stats else 0
            
            # Add metrics for test stats
            result.add_metric("Total Tests", total_tests, "tests")
            result.add_metric("Passed Tests", passed_tests, "tests", is_better="higher")
            if failed_tests > 0:
                result.add_metric("Failed Tests", failed_tests, "tests", threshold=0, is_better="lower")
            if error_tests > 0:
                result.add_metric("Error Tests", error_tests, "tests", threshold=0, is_better="lower")
            if skipped_tests > 0:
                result.add_metric("Skipped Tests", skipped_tests, "tests")
            
            # Log test results
            if failed_tests > 0:
                logger.warning(f"{failed_tests} out of {total_tests} tests failed")
                logger.warning("This indicates potential issues but won't stop execution")
                result.summary = f"Tests failed: {failed_tests} out of {total_tests} tests failed"
            else:
                logger.info(f"All {total_tests} tests passed successfully")
                result.summary = f"Tests passed: {total_tests} tests executed successfully"
        
        except Exception as e:
            error_msg = f"Error during test execution: {type(e).__name__}: {str(e)}"
            logger.error(error_msg)
            result.summary = "Test execution failed with error"
            result.add_error(error_msg, "Test Execution Error", logger.format_exc() if hasattr(logger, 'format_exc') else None)
            return result

        # If tests failed or had errors, perform error analysis
        if not test_success:
            if config.general.trusty_agents.run_error_analysis:
                error_analysis = self.error_analyzer.analyze_failure(
                    protoblock, 
                    test_results,
                    codebase
                )
                result.add_report(error_analysis, "Error Analysis")
            
            # Final result
            return result
        else:
            # Tests passed successfully
            result.success = True
            return result

    def get_test_stats(self) -> dict:
        """Get the current test statistics"""
        return self._test_stats.copy()

    def _full_cache_bust(self):
        """
        Remove all .pyc files and __pycache__ directories from the project root and subdirectories.
        Aggressively clear sys.modules of any user code (all modules corresponding to .py files in the project, except stdlib and site-packages).
        """
        import site
        import importlib.util
        project_root = os.path.abspath(os.getcwd())
        # Remove all .pyc files
        for pyc in glob.glob(f'{project_root}/**/*.pyc', recursive=True):
            try:
                os.remove(pyc)
                logger.debug(f"Removed pyc: {pyc}")
            except Exception as e:
                logger.debug(f"Failed to remove pyc {pyc}: {e}")
        # Remove all __pycache__ dirs
        for pycache in glob.glob(f'{project_root}/**/__pycache__', recursive=True):
            try:
                shutil.rmtree(pycache)
                logger.debug(f"Removed __pycache__: {pycache}")
            except Exception as e:
                logger.debug(f"Failed to remove __pycache__ {pycache}: {e}")
        # Remove user modules from sys.modules
        stdlib_paths = set(site.getsitepackages() + [os.path.dirname(os.__file__)])
        to_delete = []
        for name, mod in list(sys.modules.items()):
            if not hasattr(mod, '__file__') or mod.__file__ is None:
                continue
            mod_path = os.path.abspath(mod.__file__)
            if any(mod_path.startswith(std) for std in stdlib_paths):
                continue
            if mod_path.startswith(project_root):
                to_delete.append(name)
        for name in to_delete:
            try:
                del sys.modules[name]
                logger.debug(f"Deleted user module from sys.modules: {name}")
            except Exception as e:
                logger.debug(f"Failed to delete user module {name}: {e}")

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
            # Full cache bust before running tests
            self._full_cache_bust()
            # Clear pytest cache to ensure fresh test discovery
            self._clear_pytest_cache()
            # Reload modules to ensure we're using the latest code
            self._reload_modules()
            if not os.path.exists(full_path):
                logger.info(f"Test path not found: {full_path}. Creating directory.")
                os.makedirs(full_path, exist_ok=True)
            reporter = CustomReporter()
            plugins = [reporter]
            if os.getcwd() not in sys.path:
                sys.path.insert(0, os.getcwd())
            args = ['-v', '--disable-warnings', '--cache-clear']
            if os.path.isfile(test_target):
                args.append(test_target)
            else:
                exclude_performance_tests = config.safe_get('general', 'trusty_agents', 'exclude_performance_tests')
                if exclude_performance_tests:
                    args.extend(['-m', 'not performance and not transient', test_target])
                else:
                    args.append(test_target)
            logger.info(f"Running pytest with args: {' '.join(args)}")
            exit_code = pytest.main(args, plugins=plugins)
            self.test_functions = reporter.test_functions
            self._test_stats = reporter.results
            self._print_test_summary(self._test_stats)
            self.test_results = "\n".join(reporter.output_lines)
            if self.test_results:
                self.test_results += "\n\n"
            summary = self._generate_summary(self._test_stats, exit_code)
            self.test_results += summary
            logger.debug(f"Test Results:\n{self.test_results}")
            execution_ok = exit_code in [0, 5]
            no_test_failures = self._test_stats['failed'] == 0 and self._test_stats['error'] == 0
            test_success = execution_ok and no_test_failures
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

    def _reload_modules(self):
        """
        Aggressively remove all relevant modules from sys.modules to ensure pytest does not use any cached code.
        This includes both test modules and TAC modules when modifying the TAC repository itself.
        """
        try:
            loaded_modules = list(sys.modules.keys())
            modules_to_remove = [
                m for m in loaded_modules if 
                ('test_' in m or m.endswith('_test') or m.startswith('tac.')) and m in sys.modules
            ]
            for module_name in modules_to_remove:
                try:
                    del sys.modules[module_name]
                    logger.debug(f"Deleted module from sys.modules: {module_name}")
                except Exception as e:
                    logger.debug(f"Failed to delete module {module_name}: {e}")
            logger.debug(f"Deleted {len(modules_to_remove)} modules from sys.modules for cache busting")
        except Exception as e:
            logger.debug(f"Error during module cache busting: {e}")

    def _clear_pytest_cache(self):
        """
        Clear pytest cache to ensure fresh test discovery.
        This helps when new tests have been added or existing tests modified.
        """
        try:
            if os.path.exists('.pytest_cache'):
                shutil.rmtree('.pytest_cache')
                logger.debug("Removed pytest cache directory")
            
            test_dir = config.general.test_path or 'tests'
            if os.path.isdir(test_dir):
                for root, dirs, files in os.walk(test_dir):
                    if '__pycache__' in dirs:
                        pycache_path = os.path.join(root, '__pycache__')
                        shutil.rmtree(pycache_path)
                        logger.debug(f"Removed {pycache_path}")
            
            if os.path.isdir(test_dir):
                for root, dirs, files in os.walk(test_dir):
                    for file in files:
                        if file.endswith('.pyc'):
                            pyc_path = os.path.join(root, file)
                            os.remove(pyc_path)
                            logger.debug(f"Removed {pyc_path}")
                            
            logger.debug("Cleared pytest cache")
        except Exception as e:
            logger.debug(f"Error clearing pytest cache: {e}")

class ErrorAnalyzer:
    """Analyzes test errors using LLMs to provide insightful feedback."""
    
    def __init__(self):
        """Initialize the error analyzer with an LLM client."""
        self.llm_client = LLMClient(component="pytest_agent")
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
            use_summaries = config.general.use_file_summaries
            logger.info(f"Using file summaries: {use_summaries}")
            logger.info("Formatting codebase for LLM prompt")
            codebase_content = []
            
            if isinstance(codebase, str):
                codebase_content.append(f"Codebase Content:\n```python\n{codebase}\n```")
            else:
                logger.debug(f"Codebase files to analyze: {list(codebase.keys())}")
                for path, content in codebase.items():
                    logger.debug(f"Processing file: {path}")
                    if use_summaries:
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
            
            analysis_prompt = f"""<purpose>
You are a senior python software engineer analyzing a failed implementation attempt. Your goal is to provide a clear and detailed analysis of what went wrong and suggest specific improvements. The information for the junior software engineer who failed at their attempt is given in the <protoblock> section, the codebase in <codebase_str>, the test results in <test_results>. Your concrete analysis rules are given in <analysis_rules>.
</purpose>

<codebase_state>
{codebase_str}
</codebase_state>

<protoblock>
Task Description: {protoblock.task_description}
Write Files: {protoblock.write_files}
Context Files: {protoblock.context_files}
Test Specification: {protoblock.trusty_agent_prompts.get("pytest", "No test specification provided")}
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
        if report.nodeid not in self.test_functions:
            self.test_functions.append(report.nodeid)
        if report.when == 'call':
            if report.passed:
                self.results['passed'] += 1
            elif report.failed:
                self.results['failed'] += 1
        elif report.when in ['setup', 'teardown']:
            if report.outcome == 'failed':
                self.results['error'] += 1
            elif report.outcome == 'skipped':
                self.results['skipped'] += 1
        if hasattr(report, 'longrepr') and report.longrepr:
            self.output_lines.append(str(report.longrepr))
    
    def pytest_collectreport(self, report):
        if report.result:
            for item in report.result:
                if hasattr(item, 'nodeid') and item.nodeid not in self.test_functions:
                    self.test_functions.append(item.nodeid)
        
        if hasattr(report, 'outcome') and report.outcome == 'failed':
            if hasattr(report, 'longrepr'):
                self.output_lines.append(f"Collection error: {report.longrepr}")
                self.results['error'] += 1
                      