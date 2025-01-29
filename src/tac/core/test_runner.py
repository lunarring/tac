import os
import logging
import pytest
from colorama import init, Fore, Style

logger = logging.getLogger(__name__)

class TestRunner:
    """
    A dedicated class for handling test execution and reporting using pytest.
    """
    def __init__(self):
        init()  # Initialize colorama
        self.test_results = ""
        
    def run_tests(self, test_path: str = None) -> bool:
        """
        Runs the tests using pytest framework.
        Args:
            test_path: Optional path to test file or directory. If None, runs all tests/test*.py files
        Returns:
            bool: True if all tests passed or no tests were found, False otherwise
        """
        try:
            # Default to running all test*.py files in tests directory
            test_target = test_path or 'tests'
            full_path = test_target
            pytest_args = ['--disable-warnings', '-v']

            logger.debug(f"Test target path: {full_path}")
            logger.debug(f"Working directory: {os.getcwd()}")
            
            if not os.path.exists(full_path):
                error_msg = f"Error: Test path not found: {full_path}"
                logger.error(error_msg)
                self.test_results = error_msg
                return False

            if os.path.isfile(full_path):
                # Single test file case
                logger.debug(f"Running single test file: {test_target}")
                result = self._run_pytest([test_target] + pytest_args)
            elif os.path.isdir(full_path):
                # Directory case - discover and run all test files
                logger.debug(f"Discovering tests in directory: {test_target}")
                result = self._run_pytest([test_target] + pytest_args)
            else:
                error_msg = f"Error: Path is neither a file nor directory: {full_path}"
                logger.error(error_msg)
                self.test_results = error_msg
                return False

            return result
            
        except Exception as e:
            error_msg = f"Error running tests: {type(e).__name__}: {str(e)}"
            logger.exception(error_msg)
            self.test_results = error_msg
            return False

    def _run_pytest(self, args: list) -> bool:
        """Run tests using pytest's Python API directly"""
        try:
            # Create a custom pytest plugin to capture output
            class OutputCapture:
                def __init__(self):
                    self.output = []
                    self.test_results = {
                        'passed': 0,
                        'failed': 0,
                        'error': 0,
                        'skipped': 0
                    }
                    self.no_tests_collected = False

                def _should_capture_output(self, text):
                    # Filter out debug and logging messages
                    if not text:
                        return False
                    text = str(text)
                    ignore_patterns = [
                        'DEBUG    ',
                        'INFO     ',
                        'WARNING  ',
                        'ERROR    ',
                        'CRITICAL ',
                        'httpcore.',
                        'httpx:',
                        'openai.',
                    ]
                    return not any(pattern in text for pattern in ignore_patterns)

                def pytest_collectreport(self, report):
                    if report.outcome == 'passed' and not report.result:
                        self.no_tests_collected = True
                    # Add collection error handling
                    if report.outcome == 'failed':
                        if hasattr(report, 'longrepr') and self._should_capture_output(report.longrepr):
                            self.output.append(str(report.longrepr))

                def pytest_runtest_logreport(self, report):
                    # Capture test results
                    if report.when == 'call':  # Only count the actual test result
                        if report.passed:
                            self.test_results['passed'] += 1
                        elif report.failed:
                            if report.when == 'setup' or report.when == 'teardown':
                                self.test_results['error'] += 1
                            else:
                                self.test_results['failed'] += 1
                    elif report.skipped:
                        self.test_results['skipped'] += 1

                    # Capture test output
                    if report.longrepr and self._should_capture_output(report.longrepr):
                        self.output.append(str(report.longrepr))
                    if hasattr(report, 'caplog') and self._should_capture_output(report.caplog):
                        self.output.append(report.caplog)
                    if hasattr(report, 'capstdout') and self._should_capture_output(report.capstdout):
                        self.output.append(report.capstdout)
                    if hasattr(report, 'capstderr') and self._should_capture_output(report.capstderr):
                        self.output.append(report.capstderr)

            output_capture = OutputCapture()
            
            # Add verbosity if not already present
            if '-v' not in args and '-vv' not in args:
                args.append('-v')
            
            # Run pytest with our output capture plugin
            result = pytest.main(args, plugins=[output_capture])
            
            # Create summary from captured results
            summary = "\nTest Summary:\n"
            if output_capture.no_tests_collected and not output_capture.output:
                summary = "\nNo tests were found in the specified path.\n"
                summary += "This is not a failure - it just means no tests exist yet.\n"
            else:
                # If we have output but no test results, it's likely a collection error
                if not any(output_capture.test_results.values()) and output_capture.output:
                    summary = "\nTest Collection Error:\n"
                else:
                    summary += f"Passed: {output_capture.test_results['passed']}\n"
                    if output_capture.test_results['failed'] > 0:
                        summary += f"Failed: {output_capture.test_results['failed']}\n"
                    if output_capture.test_results['error'] > 0:
                        summary += f"Errors: {output_capture.test_results['error']}\n"
                    if output_capture.test_results['skipped'] > 0:
                        summary += f"Skipped: {output_capture.test_results['skipped']}\n"
            
            # Combine captured output with summary
            full_output = '\n'.join(filter(None, output_capture.output))  # Filter out empty strings
            if full_output:
                full_output = f"\nDetailed Output:\n{full_output}\n"
            full_output += summary
            
            # Map pytest exit codes to meaningful messages
            exit_code_messages = {
                pytest.ExitCode.OK: "All tests passed!",
                pytest.ExitCode.TESTS_FAILED: "Some tests failed",
                pytest.ExitCode.INTERRUPTED: "Testing was interrupted",
                pytest.ExitCode.INTERNAL_ERROR: "Internal error in pytest",
                pytest.ExitCode.USAGE_ERROR: "Pytest usage error",
                pytest.ExitCode.NO_TESTS_COLLECTED: "No tests were found",
            }
            
            # Get meaningful message for the exit code
            result_message = exit_code_messages.get(result, f"Unknown pytest exit code: {result}")
            
            # Store both the result message and the full output
            self.test_results = f"Test execution completed. Result: {result_message}\n{full_output}"
            
            # Special case: if no tests were collected and no errors, treat this as success
            if result == pytest.ExitCode.NO_TESTS_COLLECTED and not output_capture.output:
                print("\nNo tests were found. This is not a failure - proceeding with implementation.")
                return True
            
            # Print test summary
            self._print_test_summary(output_capture.test_results)
            
            # Only print error details if tests didn't pass
            if result != pytest.ExitCode.OK and output_capture.output:
                print("\nDetailed Output:")
                print(full_output)
            
            return result == pytest.ExitCode.OK
            
        except Exception as e:
            error_msg = f"Error running pytest: {str(e)}\n{type(e).__name__}: {str(e)}"
            logger.error(error_msg)
            self.test_results = error_msg
            print(f"\nTest Error: {error_msg}")
            return False

    def _print_test_summary(self, results: dict):
        """Print a colored test summary"""
        total = sum(results.values())
        if total == 0:
            return

        # Determine overall color
        if results['failed'] > 0 or results['error'] > 0:
            color = Fore.RED
        elif results['passed'] == total:
            color = Fore.GREEN
        else:
            color = Fore.YELLOW

        # Print summary
        print("\n" + "="*50)
        print(f"{color}Test Summary:{Style.RESET_ALL}")
        
        if results['failed'] > 0 or results['error'] > 0:
            print(f"{Fore.RED}Passed: {results['passed']}/{total}{Style.RESET_ALL}")
            if results['failed'] > 0:
                print(f"{Fore.RED}Failed: {results['failed']}{Style.RESET_ALL}")
            if results['error'] > 0:
                print(f"{Fore.RED}Errors: {results['error']}{Style.RESET_ALL}")
        else:
            print(f"{Fore.GREEN}Passed: {results['passed']}/{total}{Style.RESET_ALL}")
        
        if results['skipped'] > 0:
            print(f"{Fore.YELLOW}Skipped: {results['skipped']}{Style.RESET_ALL}")
        print("="*50)

    def get_test_results(self) -> str:
        """Get the full test results including output and summary"""
        return self.test_results 