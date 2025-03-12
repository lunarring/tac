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


class PexpectTestingAgent(TrustyAgent):
    """
    A trusty agent that performs end-to-end testing using Pexpect.
    """
    # Registration information
    agent_name = "pexpect"
    protoblock_prompt = """
Define end-to-end tests to verify the functionality through the command line interface. These tests will use pexpect to interact with the program as a user would.

Format your tests in a code block with the following structure:
```e2e_tests
[
  {
    "name": "Test Name",
    "description": "Description of what this test verifies",
    "commands": [
      "command to run",
      "next command"
    ],
    "expected_outputs": [
      "expected output from first command",
      "expected output from second command"
    ],
    "timeout": 10,  # Optional, defaults to 10 seconds
    "exit_code": 0  # Optional, defaults to 0
  }
]
```

The test will:
1. Run each command in sequence
2. Check if the output contains the expected text
3. Verify the exit code of the last command

Tips:
- Use regular expressions in expected_outputs for flexible matching
- Keep commands simple and focused on one action
- Include assertions for both positive and negative cases
- Test edge cases and error handling
"""
    description = "A trusty agent that performs end-to-end testing using Pexpect. Requires E2E test specification in the format ```e2e_tests [...]```."
    
    def __init__(self):
        self.test_results = []
        self.runner = E2ETestRunner()
        self.report = ""
        
    def _check_impl(self, protoblock, codebase, code_diff):
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
            # Check if pexpect section exists in the protoblock
            if not hasattr(protoblock, 'pexpect') or not hasattr(protoblock.pexpect, 'specification'):
                logger.info("No pexpect specification found in the protoblock - skipping E2E tests")
                return True, "", ""
                
            # Check if the specification is empty or doesn't contain any tests
            if not protoblock.pexpect.specification or not protoblock.pexpect.specification.strip():
                logger.info("Empty pexpect specification - skipping E2E tests")
                return True, "", ""
                
            # Extract test cases from the test specification
            test_cases = self._parse_test_cases(protoblock.pexpect.specification)
            
            if not test_cases:
                logger.warning("No E2E test cases found in the test specification")
                # Return a helpful message about how to define tests
                help_message = """
No E2E test cases were found in the specification. To define E2E tests, add a code block like this:

```e2e_tests
[
  {
    "name": "Test Command Execution",
    "description": "Verify that the command runs successfully",
    "commands": [
      "python my_script.py --arg value"
    ],
    "expected_outputs": [
      "Expected output text"
    ],
    "timeout": 10,
    "exit_code": 0
  }
]
```

Each test should include:
- A descriptive name
- Commands to run
- Expected outputs to verify
- Optional timeout and exit code values
"""
                return True, help_message, "No E2E tests defined"
                
            logger.info(f"Found {len(test_cases)} E2E test cases to run")
            
            # Run the tests
            self.test_results = self.runner.run_tests(test_cases)
            self.report = self.runner.generate_report()
            
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
            traceback.print_exc()  # Print the full traceback for debugging
            return False, error_msg, "E2E test execution error"
    
    def _parse_test_cases(self, specification: str) -> List[E2ETestCase]:
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
            specification: The test specification from the ProtoBlock
            
        Returns:
            List[E2ETestCase]: Parsed test cases
        """
        test_cases = []
        
        if not specification:
            logger.warning("Empty test specification provided")
            return test_cases
            
        # Look for e2e_tests section
        e2e_section_match = re.search(r'```e2e_tests\s*([\s\S]*?)\s*```', specification)
        if not e2e_section_match:
            logger.warning("No e2e_tests code block found in the specification")
            return test_cases
            
        try:
            # Parse JSON array of test cases
            test_cases_json = json.loads(e2e_section_match.group(1))
            
            if not isinstance(test_cases_json, list):
                logger.error("E2E test specification must be a JSON array")
                return test_cases
                
            for i, tc in enumerate(test_cases_json):
                # Validate required fields
                if not isinstance(tc, dict):
                    logger.warning(f"Test case #{i+1} is not a valid JSON object, skipping")
                    continue
                    
                if 'name' not in tc:
                    logger.warning(f"Test case #{i+1} is missing a name, using default")
                    
                if 'commands' not in tc or not tc['commands']:
                    logger.warning(f"Test case '{tc.get('name', f'#{i+1}')}' has no commands, skipping")
                    continue
                    
                if not isinstance(tc.get('commands', []), list):
                    logger.warning(f"Test case '{tc.get('name', f'#{i+1}')}' commands must be a list, skipping")
                    continue
                    
                # Create test case with defaults for optional fields
                test_case = E2ETestCase(
                    name=tc.get('name', f'Test case #{i+1}'),
                    commands=tc.get('commands', []),
                    expected_outputs=tc.get('expected_outputs', []),
                    timeout=tc.get('timeout', 10),
                    exit_code=tc.get('exit_code', 0),
                    description=tc.get('description', '')
                )
                
                # Validate and normalize expected outputs
                if len(test_case.expected_outputs) > 0 and len(test_case.expected_outputs) < len(test_case.commands):
                    logger.warning(f"Test case '{test_case.name}' has fewer expected outputs than commands")
                    # Pad with empty strings to match command count
                    test_case.expected_outputs.extend([''] * (len(test_case.commands) - len(test_case.expected_outputs)))
                
                test_cases.append(test_case)
                logger.info(f"Parsed test case: {test_case.name} with {len(test_case.commands)} commands")
                
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
            if result.test_case.description:
                analysis.append(f"**Description:** {result.test_case.description}")
            analysis.append(f"**Error:** {result.error_message}")
            analysis.append("")
            
            analysis.append("**Commands executed:**")
            for cmd in result.test_case.commands:
                analysis.append(f"- `{cmd}`")
            analysis.append("")
            
            analysis.append("**Expected outputs:**")
            for output in result.test_case.expected_outputs:
                if output:  # Only show non-empty expected outputs
                    analysis.append(f"- `{output}`")
            analysis.append("")
            
            analysis.append("**Actual output excerpt:**")
            # Show more context for the output
            output_lines = result.output.splitlines()
            if len(output_lines) > 30:
                # Show first 10 and last 20 lines if output is long
                shown_lines = output_lines[:10] + ["..."] + output_lines[-20:]
            else:
                shown_lines = output_lines
                
            analysis.append("```")
            for line in shown_lines:
                analysis.append(line)
            analysis.append("```")
            analysis.append("")
            
            # Add potential causes and suggestions
            analysis.append("**Potential causes and solutions:**")
            
            # Look for common issues
            if "command not found" in result.output:
                analysis.append("- **Command not found**: The command may not be installed or not in PATH")
                analysis.append("  - Solution: Install the required package or ensure the command is available")
                analysis.append("  - Check if there's a typo in the command name")
            elif "permission denied" in result.output.lower():
                analysis.append("- **Permission denied**: The script or command doesn't have execution permissions")
                analysis.append("  - Solution: Add execution permission with `chmod +x filename`")
                analysis.append("  - Check if you need to run with sudo for system operations")
            elif "no such file or directory" in result.output.lower():
                analysis.append("- **File not found**: The specified file or directory doesn't exist")
                analysis.append("  - Solution: Verify file paths and working directory")
                analysis.append("  - Check if the file needs to be created first by a previous command")
            elif "timeout" in result.error_message.lower():
                analysis.append("- **Timeout**: Command took too long to execute or produce expected output")
                analysis.append("  - Solution: Increase the timeout value for this test case")
                analysis.append("  - Check if the command is stuck in a loop or waiting for input")
            elif "expected output" in result.error_message.lower():
                analysis.append("- **Output mismatch**: The command didn't produce the expected output")
                analysis.append("  - Solution: Check if the expected output pattern is correct")
                analysis.append("  - Consider using regex patterns for more flexible matching")
                analysis.append("  - Verify that the command produces consistent output")
            elif "exit code" in result.error_message.lower():
                analysis.append("- **Exit code mismatch**: The command exited with an unexpected status code")
                analysis.append("  - Solution: Check if the command is failing for a valid reason")
                analysis.append("  - Verify that the expected exit code is correct")
            else:
                analysis.append("- **Unexpected behavior**: The command didn't behave as expected")
                analysis.append("  - Solution: Review the command and its expected behavior")
                analysis.append("  - Check if environment variables or system state affect the command")
                
            analysis.append("")
            
            # Add specific suggestions based on the test case
            analysis.append("**Specific suggestions:**")
            
            # Check if the expected output might need to be a regex
            for expected in result.test_case.expected_outputs:
                if expected and not expected.startswith('regex:') and any(c in expected for c in '*+?[](){}|^$'):
                    analysis.append(f"- The expected output `{expected}` contains regex special characters. Consider using `regex:` prefix for pattern matching.")
            
            # Check if the timeout might be too short
            if "timeout" in result.error_message.lower() and result.test_case.timeout < 30:
                analysis.append(f"- The current timeout ({result.test_case.timeout}s) might be too short. Consider increasing it for commands that take longer to execute.")
            
            analysis.append("")
            
        # Add example of a fixed test if there are failures
        if failed_tests:
            analysis.extend(self._suggest_example_tests(codebase))
            
        return "\n".join(analysis)
        
    def _suggest_example_tests(self, codebase: Dict[str, str]) -> List[str]:
        """
        Suggest example tests based on the codebase.
        
        Args:
            codebase: Dictionary mapping file paths to their contents
            
        Returns:
            List[str]: Lines of text with example test suggestions
        """
        suggestions = [
            "## Example Test Suggestions",
            "",
            "Here are some example tests that might help you get started:"
        ]
        
        # Look for Python files in the codebase
        python_files = [path for path in codebase.keys() if path.endswith('.py')]
        
        # If we found Python files, suggest a basic test for the first one
        if python_files:
            main_file = next((f for f in python_files if 'main.py' in f), python_files[0])
            file_basename = os.path.basename(main_file)
            
            suggestions.extend([
                "",
                "### Basic Script Execution Test",
                "```e2e_tests",
                "[",
                "  {",
                f'    "name": "Test {file_basename} Execution",',
                f'    "description": "Verify that {file_basename} runs without errors",',
                "    \"commands\": [",
                f'      "python {main_file}"',
                "    ],",
                "    \"expected_outputs\": [",
                "      \"regex:.*\"  // This will match any output",
                "    ],",
                "    \"timeout\": 10,",
                "    \"exit_code\": 0",
                "  }",
                "]",
                "```"
            ])
            
            # Look for help flags or arguments in the file
            with open(main_file, 'r') as f:
                content = f.read()
                
            if 'argparse' in content or '--help' in content:
                suggestions.extend([
                    "",
                    "### Help Command Test",
                    "```e2e_tests",
                    "[",
                    "  {",
                    f'    "name": "Test {file_basename} Help Option",',
                    f'    "description": "Verify that {file_basename} displays help information",',
                    "    \"commands\": [",
                    f'      "python {main_file} --help"',
                    "    ],",
                    "    \"expected_outputs\": [",
                    "      \"regex:usage:.*\"",
                    "    ],",
                    "    \"timeout\": 5,",
                    "    \"exit_code\": 0",
                    "  }",
                    "]",
                    "```"
                ])
        
        # Add a general example for any command-line tool
        suggestions.extend([
            "",
            "### General Command Test Template",
            "```e2e_tests",
            "[",
            "  {",
            '    "name": "Test Command With Arguments",',
            '    "description": "Verify that the command processes arguments correctly",',
            "    \"commands\": [",
            '      "your_command --arg1 value1 --arg2 value2"',
            "    ],",
            "    \"expected_outputs\": [",
            "      \"Expected output text\",",
            "      \"regex:Pattern with .* wildcards\"",
            "    ],",
            "    \"timeout\": 15,",
            "    \"exit_code\": 0",
            "  },",
            "  {",
            '    "name": "Test Multi-Step Process",',
            '    "description": "Test a sequence of commands that work together",',
            "    \"commands\": [",
            '      "command1 > output.txt",',
            '      "command2 < output.txt"',
            "    ],",
            "    \"expected_outputs\": [",
            "      \"\",  // No specific output expected for first command",
            "      \"Expected output from second command\"",
            "    ],",
            "    \"timeout\": 20,",
            "    \"exit_code\": 0",
            "  }",
            "]",
            "```",
            "",
            "Remember to adapt these examples to your specific application and requirements."
        ])
        
        return suggestions
    
    def get_test_results(self) -> str:
        """
        Get the formatted test results.
        
        Returns:
            str: Formatted test report
        """
        return self.report 

# Register this agent
PexpectTestingAgent.register() 