import os
import logging
import pytest
from colorama import init, Fore, Style
from _pytest.main import Session
from _pytest.reports import TestReport
from _pytest.terminal import TerminalReporter
import sys
import re
import shutil

logger = logging.getLogger(__name__)

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

class TestRunner:
    """
    A dedicated class for handling test execution and reporting using pytest.
    """
    def __init__(self):
        init()  # Initialize colorama
        self.test_results = ""
        self.test_functions = []
        self.had_execution_error = False
        self._test_stats = {'passed': 0, 'failed': 0, 'error': 0, 'skipped': 0}
        
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
            args = ['-v', '--disable-warnings', test_target]
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

def test_pytest_cache_cleanup(tmp_path, monkeypatch):
    work_dir = tmp_path / "work_dir"
    work_dir.mkdir()
    cache_dir = work_dir / ".pytest_cache"
    cache_dir.mkdir()
    (cache_dir / "dummy.txt").write_text("dummy")

    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "test_dummy.py").write_text("def test_dummy():\n    pass\n")

    monkeypatch.setattr(os, "getcwd", lambda: str(work_dir))

    from src.tac.core.test_runner import TestRunner
    tr = TestRunner()
    tr.run_tests(test_path=str(test_dir))
    assert not cache_dir.exists()
