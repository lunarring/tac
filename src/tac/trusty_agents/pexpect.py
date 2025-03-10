import os
import sys
import re
import time
import json
import tempfile
from typing import Dict, Tuple, List, Optional, Any
from dataclasses import dataclass, field
import pexpect
from pexpect import spawn, TIMEOUT, EOF

from tac.blocks import ProtoBlock
from tac.trusty_agents.base import TrustyAgent
from tac.core.config import config
from tac.core.log_config import setup_logging

logger = setup_logging('tac.trusty_agents.pexpect')


@dataclass
class E2ETestCase:
    """
    Represents a single end-to-end test case with commands and expected outputs.
    """
    name: str
    commands: List[str]
    expected_outputs: List[str]
    timeout: int = 10
    exit_code: Optional[int] = 0
    description: str = ""
    

@dataclass
class E2ETestResult:
    """
    Stores the result of an end-to-end test execution.
    """
    test_case: E2ETestCase
    success: bool
    output: str
    error_message: str = ""
    execution_time: float = 0.0


class E2ETestRunner:
    """
    Handles the execution of end-to-end tests using pexpect.
    """
    def __init__(self, working_dir: str = None):
        self.working_dir = working_dir or os.getcwd()
        self.results: List[E2ETestResult] = []
        self.current_process = None
        
    def run_test(self, test_case: E2ETestCase) -> E2ETestResult:
        """
        Run a single end-to-end test case.
        
        Args:
            test_case: The test case to run
            
        Returns:
            E2ETestResult: The result of the test execution
        """
        logger.info(f"Running E2E test: {test_case.name}")
        start_time = time.time()
        
        # Create a temporary file to capture output
        with tempfile.NamedTemporaryFile(mode='w+', delete=False) as temp_file:
            temp_filename = temp_file.name
        
        try:
            # Start with a clean process
            shell_cmd = os.environ.get('SHELL', '/bin/bash')
            self.current_process = pexpect.spawn(
                shell_cmd, 
                cwd=self.working_dir,
                encoding='utf-8',
                logfile=open(temp_filename, 'w')
            )
            
            # Execute each command and check for expected outputs
            for i, command in enumerate(test_case.commands):
                logger.debug(f"Sending command: {command}")
                self.current_process.sendline(command)
                
                # Check for expected output if specified
                if i < len(test_case.expected_outputs) and test_case.expected_outputs[i]:
                    expected = test_case.expected_outputs[i]
                    
                    # Handle regex patterns
                    if expected.startswith('regex:'):
                        pattern = expected[6:]  # Remove 'regex:' prefix
                        try:
                            index = self.current_process.expect([re.compile(pattern)], timeout=test_case.timeout)
                            if index != 0:
                                raise Exception(f"Expected pattern '{pattern}' not found")
                        except TIMEOUT:
                            raise Exception(f"Timeout waiting for pattern '{pattern}'")
                    else:
                        try:
                            index = self.current_process.expect([expected], timeout=test_case.timeout)
                            if index != 0:
                                raise Exception(f"Expected output '{expected}' not found")
                        except TIMEOUT:
                            raise Exception(f"Timeout waiting for '{expected}'")
            
            # Check exit code if specified
            if test_case.exit_code is not None:
                self.current_process.sendline("echo $?")
                self.current_process.expect([r"(\d+)"], timeout=test_case.timeout)
                actual_exit_code = int(self.current_process.match.group(1))
                if actual_exit_code != test_case.exit_code:
                    raise Exception(f"Expected exit code {test_case.exit_code}, got {actual_exit_code}")
            
            # Test passed
            execution_time = time.time() - start_time
            
            # Read the output from the temp file
            with open(temp_filename, 'r') as f:
                output = f.read()
                
            result = E2ETestResult(
                test_case=test_case,
                success=True,
                output=output,
                execution_time=execution_time
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            
            # Read the output from the temp file
            with open(temp_filename, 'r') as f:
                output = f.read()
                
            result = E2ETestResult(
                test_case=test_case,
                success=False,
                output=output,
                error_message=str(e),
                execution_time=execution_time
            )
            logger.error(f"E2E test '{test_case.name}' failed: {str(e)}")
            
        finally:
            # Clean up
            if self.current_process and self.current_process.isalive():
                self.current_process.sendline("exit")
                self.current_process.close()
            
            # Remove temp file
            if os.path.exists(temp_filename):
                os.unlink(temp_filename)
                
        self.results.append(result)
        return result
    
    def run_tests(self, test_cases: List[E2ETestCase]) -> List[E2ETestResult]:
        """
        Run multiple end-to-end test cases.
        
        Args:
            test_cases: List of test cases to run
            
        Returns:
            List[E2ETestResult]: Results of all test executions
        """
        self.results = []
        for test_case in test_cases:
            self.run_test(test_case)
        return self.results
    
    def generate_report(self) -> str:
        """
        Generate a human-readable report of test results.
        
        Returns:
            str: Formatted test report
        """
        if not self.results:
            return "No tests were run."
            
        total = len(self.results)
        passed = sum(1 for r in self.results if r.success)
        failed = total - passed
        
        report = [
            f"E2E Test Results Summary",
            f"======================",
            f"Total tests: {total}",
            f"Passed: {passed}",
            f"Failed: {failed}",
            f"Success rate: {passed/total*100:.1f}%",
            f"",
            f"Detailed Results:",
            f"----------------"
        ]
        
        for i, result in enumerate(self.results, 1):
            status = "PASSED" if result.success else "FAILED"
            report.append(f"{i}. {result.test_case.name}: {status} ({result.execution_time:.2f}s)")
            if not result.success:
                report.append(f"   Error: {result.error_message}")
                report.append(f"   Output excerpt:")
                # Add the last few lines of output for context
                output_lines = result.output.splitlines()[-10:] if result.output else []
                for line in output_lines:
                    report.append(f"     {line}")
            report.append("")
            
        return "\n".join(report)


class PexpectTestingAgent(TrustyAgent):
    """
    A trusty agent that uses Pexpect to perform end-to-end testing of command-line applications.
    """
    def __init__(self):
        self.test_runner = E2ETestRunner()
        self.test_results = []
        self.report = ""
        
    def _check_impl(self, protoblock: ProtoBlock, codebase: Dict[str, str], code_diff: str) -> Tuple[bool, str, str]:
        """
        Run end-to-end tests and check if they pass.
        
        Args:
            protoblock: The ProtoBlock containing task specifications
            codebase: Dictionary mapping file paths to their contents
            code_diff: The git diff showing implemented changes
            
        Returns:
            Tuple containing:
            - bool: Success status (True if tests passed, False otherwise)
            - str: Error analysis (empty string if success is True)
            - str: Failure type description (empty string if success is True)
        """
        logger.info("Starting E2E testing with Pexpect")
        
        try:
            # Extract test cases from the test specification
            test_cases = self._parse_test_cases(protoblock.pytest_specification)
            
            if not test_cases:
                logger.warning("No E2E test cases found in the test specification")
                return True, "", ""
                
            logger.info(f"Found {len(test_cases)} E2E test cases to run")
            
            # Run the tests
            self.test_results = self.test_runner.run_tests(test_cases)
            self.report = self.test_runner.generate_report()
            
            # Check if all tests passed
            all_passed = all(result.success for result in self.test_results)
            
            if all_passed:
                logger.info("All E2E tests passed successfully")
                return True, "", ""
            else:
                # Generate error analysis
                failed_tests = [r for r in self.test_results if not r.success]
                error_analysis = self._generate_error_analysis(failed_tests, codebase, code_diff)
                
                logger.warning(f"{len(failed_tests)} E2E tests failed")
                return False, error_analysis, "E2E test failures"
                
        except Exception as e:
            error_msg = f"Error during E2E test execution: {type(e).__name__}: {str(e)}"
            logger.error(error_msg)
            return False, error_msg, "E2E test execution error"
    
    def _parse_test_cases(self, pytest_specification: str) -> List[E2ETestCase]:
        """
        Parse test cases from the test specification.
        
        The test specification should contain a section marked with:
        ```e2e_tests
        [
            {
                "name": "Test case name",
                "commands": ["command1", "command2"],
                "expected_outputs": ["output1", "output2"],
                "timeout": 10,
                "exit_code": 0,
                "description": "Test description"
            }
        ]
        ```
        
        Args:
            pytest_specification: The test specification from the ProtoBlock
            
        Returns:
            List[E2ETestCase]: Parsed test cases
        """
        test_cases = []
        
        # Look for e2e_tests section
        e2e_section_match = re.search(r'```e2e_tests\s*([\s\S]*?)\s*```', pytest_specification)
        if not e2e_section_match:
            return test_cases
            
        try:
            # Parse JSON array of test cases
            test_cases_json = json.loads(e2e_section_match.group(1))
            
            for tc in test_cases_json:
                test_case = E2ETestCase(
                    name=tc.get('name', 'Unnamed test'),
                    commands=tc.get('commands', []),
                    expected_outputs=tc.get('expected_outputs', []),
                    timeout=tc.get('timeout', 10),
                    exit_code=tc.get('exit_code', 0),
                    description=tc.get('description', '')
                )
                test_cases.append(test_case)
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse E2E test cases: {str(e)}")
            
        return test_cases
    
    def _generate_error_analysis(self, failed_tests: List[E2ETestResult], codebase: Dict[str, str], code_diff: str) -> str:
        """
        Generate detailed error analysis for failed tests.
        
        Args:
            failed_tests: List of failed test results
            codebase: Dictionary mapping file paths to their contents
            code_diff: The git diff showing implemented changes
            
        Returns:
            str: Detailed error analysis
        """
        analysis = ["# E2E Test Failure Analysis", ""]
        
        for i, result in enumerate(failed_tests, 1):
            analysis.append(f"## {i}. Test Case: {result.test_case.name}")
            analysis.append(f"**Error:** {result.error_message}")
            analysis.append("")
            analysis.append("**Commands executed:**")
            for cmd in result.test_case.commands:
                analysis.append(f"- `{cmd}`")
            analysis.append("")
            
            analysis.append("**Expected outputs:**")
            for output in result.test_case.expected_outputs:
                analysis.append(f"- `{output}`")
            analysis.append("")
            
            analysis.append("**Actual output excerpt:**")
            output_lines = result.output.splitlines()[-20:] if result.output else []
            analysis.append("```")
            for line in output_lines:
                analysis.append(line)
            analysis.append("```")
            analysis.append("")
            
            # Add potential causes and suggestions
            analysis.append("**Potential causes:**")
            
            # Look for common issues
            if "command not found" in result.output:
                analysis.append("- Command not found: Check if the required executable is installed and in PATH")
            elif "permission denied" in result.output.lower():
                analysis.append("- Permission denied: Check file permissions")
            elif "no such file or directory" in result.output.lower():
                analysis.append("- File not found: Check file paths and working directory")
            elif "timeout" in result.error_message.lower():
                analysis.append("- Timeout: Command took too long to execute or produce expected output")
            else:
                analysis.append("- Unexpected output: The command did not produce the expected output")
                
            analysis.append("")
            
        return "\n".join(analysis)
    
    def get_test_results(self) -> str:
        """
        Get the formatted test results.
        
        Returns:
            str: Formatted test report
        """
        return self.report 