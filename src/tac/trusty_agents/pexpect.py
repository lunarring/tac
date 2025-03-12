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
import traceback

from tac.blocks import ProtoBlock
from tac.trusty_agents.base import TrustyAgent, trusty_agent
from tac.core.config import config
from tac.core.log_config import setup_logging

logger = setup_logging('tac.trusty_agents.pexpect')


# @dataclass
# class E2ETestCase:
    """
    Represents a single end-to-end test case with commands and expected outputs.
    """
    name: str
    commands: List[str]
    expected_outputs: List[str]
    timeout: int = 10
    exit_code: Optional[int] = 0
    description: str = ""
    
# @dataclass
# class E2ETestResult:
    """
    Stores the result of an end-to-end test execution.
    """
    test_case: E2ETestCase
    success: bool
    output: str
    error_message: str = ""
    execution_time: float = 0.0


# class E2ETestRunner:
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
            
            # Set a more visible prompt to help with command separation in output
            self.current_process.sendline("export PS1='E2E_TEST_PROMPT> '")
            self.current_process.expect(['E2E_TEST_PROMPT>', pexpect.TIMEOUT], timeout=2)
            
            # Execute each command and check for expected outputs
            for i, command in enumerate(test_case.commands):
                logger.debug(f"Sending command: {command}")
                self.current_process.sendline(command)
                
                # Wait for the prompt to return, indicating command completion
                self.current_process.expect(['E2E_TEST_PROMPT>', pexpect.TIMEOUT], timeout=test_case.timeout)
                
                # Check for expected output if specified
                if i < len(test_case.expected_outputs) and test_case.expected_outputs[i]:
                    expected = test_case.expected_outputs[i]
                    
                    # Get the output since the last command was sent
                    # This is more reliable than using the full buffer
                    with open(temp_filename, 'r') as f:
                        full_output = f.read()
                    
                    # Extract the output for just this command
                    command_pattern = re.escape(command)
                    output_match = re.search(f"{command_pattern}\\r?\\n(.*?)E2E_TEST_PROMPT>", 
                                            full_output, re.DOTALL)
                    
                    if not output_match:
                        logger.warning(f"Could not extract command output for '{command}'")
                        command_output = full_output
                    else:
                        command_output = output_match.group(1)
                    
                    # Handle regex patterns
                    if expected.startswith('regex:'):
                        pattern = expected[6:]  # Remove 'regex:' prefix
                        try:
                            if not re.search(pattern, command_output, re.MULTILINE):
                                raise Exception(f"Expected pattern '{pattern}' not found in output")
                            logger.debug(f"Pattern '{pattern}' matched successfully")
                        except re.error as e:
                            raise Exception(f"Invalid regex pattern '{pattern}': {str(e)}")
                    else:
                        # For literal string matching, we'll be more flexible
                        # by ignoring whitespace differences and case
                        normalized_output = re.sub(r'\s+', ' ', command_output).strip().lower()
                        normalized_expected = re.sub(r'\s+', ' ', expected).strip().lower()
                        
                        if normalized_expected not in normalized_output:
                            raise Exception(f"Expected output '{expected}' not found in command output")
                        logger.debug(f"Expected output '{expected}' found")
            
            # Check exit code if specified
            if test_case.exit_code is not None:
                self.current_process.sendline("echo $?")
                self.current_process.expect(['E2E_TEST_PROMPT>', pexpect.TIMEOUT], timeout=test_case.timeout)
                
                # Extract the exit code from the output
                with open(temp_filename, 'r') as f:
                    exit_code_output = f.read()
                
                exit_code_match = re.search(r"echo \$\?\r?\n(\d+)", exit_code_output)
                if not exit_code_match:
                    raise Exception("Could not determine exit code")
                    
                actual_exit_code = int(exit_code_match.group(1))
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
            logger.info(f"E2E test '{test_case.name}' passed in {execution_time:.2f}s")
            
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
            "# E2E Test Results Summary",
            "=========================="
        ]
        
        # Add a visual indicator of overall success/failure
        if failed == 0:
            report.append("✅ ALL TESTS PASSED")
        else:
            report.append(f"❌ {failed} TEST(S) FAILED")
            
        report.extend([
            f"",
            f"Total tests: {total}",
            f"Passed: {passed}",
            f"Failed: {failed}",
            f"Success rate: {passed/total*100:.1f}%",
            f"Total execution time: {sum(r.execution_time for r in self.results):.2f}s",
            f"",
            f"## Detailed Results"
        ])
        
        # Group results by status
        if failed > 0:
            report.append("\n### Failed Tests")
            for i, result in enumerate([r for r in self.results if not r.success], 1):
                report.append(f"{i}. ❌ **{result.test_case.name}** ({result.execution_time:.2f}s)")
                report.append(f"   - Error: {result.error_message}")
                if result.test_case.description:
                    report.append(f"   - Description: {result.test_case.description}")
                report.append(f"   - Commands: {', '.join(f'`{cmd}`' for cmd in result.test_case.commands)}")
                
                # Add output excerpt for failed tests
                report.append(f"   - Output excerpt:")
                output_lines = result.output.splitlines()[-10:] if result.output else []
                for line in output_lines:
                    report.append(f"     {line}")
                report.append("")
        
        report.append("\n### Passed Tests")
        for i, result in enumerate([r for r in self.results if r.success], 1):
            report.append(f"{i}. ✅ **{result.test_case.name}** ({result.execution_time:.2f}s)")
            if result.test_case.description:
                report.append(f"   - Description: {result.test_case.description}")
            report.append(f"   - Commands: {', '.join(f'`{cmd}`' for cmd in result.test_case.commands[:3])}")
            if len(result.test_case.commands) > 3:
                report.append(f"     ... and {len(result.test_case.commands) - 3} more command(s)")
            report.append("")
        
        # Add recommendations section if there are failures
        if failed > 0:
            report.extend([
                "## Recommendations",
                "",
                "To fix the failing tests, consider the following general tips:",
                "",
                "1. **Check command availability**: Ensure all required commands are installed and in PATH",
                "2. **Verify expected outputs**: Make sure expected outputs match actual command output",
                "3. **Use regex patterns**: For variable outputs, use `regex:` prefix with a pattern",
                "4. **Adjust timeouts**: Increase timeouts for long-running commands",
                "5. **Check working directory**: Ensure commands are run in the correct directory",
                ""
            ])
            
        return "\n".join(report)


@trusty_agent(
    name="pexpect",
    description="A trusty agent that performs end-to-end testing using Pexpect. Great for running and end-to-end test that verifies the functionality of the entire program through the command line interface.",
    protoblock_prompt="""On basis of the pexpect library, define end-to-end tests to verify the functionality through the command line interface. These tests will use pexpect to interact with the program as a user would. Select on a high level what kind of test should be constructed here. Ensure we are using pexpect. Write the test in tests/test_<program_name>.py"""
)
class PexpectTestingAgent(TrustyAgent):
    """
    A trusty agent that performs end-to-end testing using Pexpect.
    """
    # Registration information

    
    def __init__(self):
        self.test_results = []
        self.report = ""
        
