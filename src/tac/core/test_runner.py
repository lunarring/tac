import os
import logging
import pytest
from colorama import init, Fore, Style
import subprocess
import sys
import re

logger = logging.getLogger(__name__)

class TestRunner:
    """
    A dedicated class for handling test execution and reporting using pytest.
    """
    def __init__(self):
        init()  # Initialize colorama
        self.test_results = ""
        self.test_functions = []  # Store test function names
        
    def run_tests(self, test_path: str = None) -> bool:
        """
        Runs the tests using pytest framework.
        Args:
            test_path: Optional path to test file or directory. If None, runs all tests/test*.py files
        Returns:
            bool: True if all tests passed or no tests were found, False otherwise
        """
        try:
            # Reset test functions list before each run
            self.test_functions = []
            
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
        """Run tests using subprocess to ensure clean environment"""
        try:
            # Construct command with proper Python executable and pytest module
            cmd = [sys.executable, "-m", "pytest"] + args

            # Run pytest in subprocess with output capture
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env={**os.environ, 'PYTHONPATH': os.getcwd()}
            )

            # Store the output
            output = []
            if process.stdout:
                output.append(process.stdout)
            if process.stderr:
                output.append(process.stderr)

            # Parse test results
            results = {
                'passed': 0,
                'failed': 0,
                'error': 0,
                'skipped': 0,
                'collection_error': 0
            }

            # Extract test results using regex
            if process.stdout:
                # Count passed tests
                passed_match = re.search(r'(\d+) passed', process.stdout)
                if passed_match:
                    results['passed'] = int(passed_match.group(1))

                # Count failed tests
                failed_match = re.search(r'(\d+) failed', process.stdout)
                if failed_match:
                    results['failed'] = int(failed_match.group(1))

                # Count errors
                error_match = re.search(r'(\d+) error', process.stdout)
                if error_match:
                    results['error'] = int(error_match.group(1))

                # Count skipped tests
                skipped_match = re.search(r'(\d+) skipped', process.stdout)
                if skipped_match:
                    results['skipped'] = int(skipped_match.group(1))

                # Extract test function names
                self.test_functions = re.findall(r'test_\w+', process.stdout)

            # Create summary
            summary = "\nTest Summary:\n"
            if process.returncode == 0:
                summary += "All tests passed!\n"
            elif process.returncode == 5:
                summary += "No tests were found.\n"
                summary += "This is not a failure - it just means no tests exist yet.\n"
            else:
                summary += f"Tests failed with return code {process.returncode}\n"

            summary += f"Passed: {results['passed']}\n"
            if results['failed'] > 0:
                summary += f"Failed: {results['failed']}\n"
            if results['error'] > 0:
                summary += f"Errors: {results['error']}\n"
            if results['skipped'] > 0:
                summary += f"Skipped: {results['skipped']}\n"

            # Store full results
            self.test_results = '\n'.join(output) + summary

            # Print colored summary
            self._print_test_summary(results)

            # Return True if all tests passed or no tests were found
            return process.returncode in [0, 5]

        except Exception as e:
            error_msg = f"Error running pytest: {str(e)}\n{type(e).__name__}: {str(e)}"
            logger.error(error_msg)
            self.test_results = error_msg
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

    def get_test_functions(self) -> list:
        """Get the list of collected test function names"""
        return self.test_functions 