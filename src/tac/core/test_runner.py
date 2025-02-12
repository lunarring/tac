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
        """Run tests using subprocess with real-time streaming output"""
        try:
            cmd = [sys.executable, "-m", "pytest"] + args
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env={**os.environ, 'PYTHONPATH': os.getcwd()}
            )
            output_lines = []
            # Stream output line by line in real-time
            while True:
                line = process.stdout.readline()
                if line == '' and process.poll() is not None:
                    break
                if line:
                    print(line, end='', flush=True)
                    output_lines.append(line)
            # Collect any remaining output
            remaining = process.stdout.read()
            if remaining:
                print(remaining, end='', flush=True)
                output_lines.append(remaining)
            full_output = "".join(output_lines)
            # Parse test results using regex
            results = {
                'passed': 0,
                'failed': 0,
                'error': 0,
                'skipped': 0,
                'collection_error': 0
            }
            passed_match = re.search(r'(\d+) passed', full_output)
            if passed_match:
                results['passed'] = int(passed_match.group(1))
            failed_match = re.search(r'(\d+) failed', full_output)
            if failed_match:
                results['failed'] = int(failed_match.group(1))
            error_match = re.search(r'(\d+) error', full_output)
            if error_match:
                results['error'] = int(error_match.group(1))
            skipped_match = re.search(r'(\d+) skipped', full_output)
            if skipped_match:
                results['skipped'] = int(skipped_match.group(1))
            # Extract test function names
            self.test_functions = re.findall(r'test_\w+', full_output)
            # Create summary
            summary = "\nTest Summary:\n"
            returncode = process.wait()
            if returncode == 0:
                summary += "All tests passed!\n"
            elif returncode == 5:
                summary += "No tests were found.\n"
                summary += "This is not a failure - it just means no tests exist yet.\n"
            else:
                summary += f"Tests failed with return code {returncode}\n"
            summary += f"Passed: {results['passed']}\n"
            if results['failed'] > 0:
                summary += f"Failed: {results['failed']}\n"
            if results['error'] > 0:
                summary += f"Errors: {results['error']}\n"
            if results['skipped'] > 0:
                summary += f"Skipped: {results['skipped']}\n"
            self.test_results = full_output + summary
            self._print_test_summary(results)
            return returncode in [0, 5]
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
        """Get the list of collected test function names, extracting function names after '::' if present"""
        return [s.split("::")[-1].strip() if "::" in s else s for s in self.test_functions]
