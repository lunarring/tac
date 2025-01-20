import os
import subprocess
import yaml
import logging
from tdac.core.block import Block
from tdac.agents.base import Agent

logger = logging.getLogger(__name__)

class BlockExecutor:
    def __init__(self, block: Block, config: dict = None):
        self.block = block
        self.config = config if config else self._load_config()
        # Update config with block-specific parameters
        self.config.update({
            'task_description': self.block.task_description,
            'test_specification': self.block.test_specification,
            'test_data_generation': self.block.test_data_generation,
            'write_files': self.block.write_files,
            'context_files': self.block.context_files
        })
        self.agent = block.create_agent(self.config)
        self.test_results = ""
        self.previous_error = None  # Track previous error

    def _load_config(self) -> dict:
        """Load configuration from config.yaml"""
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'config.yaml')
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)

    def execute_block(self, skip_test_generation: bool = False) -> bool:
        """
        Executes the block with test-first approach and retry logic.
        Args:
            skip_test_generation: If True, skips test generation and only implements solution
        """
        try:
            if not skip_test_generation:
                print("Generating tests first...")
                self.agent.generate_tests()

            max_retries = self.config['agents']['programming']['max_retries']
            for attempt in range(max_retries):
                print(f"\nAttempt {attempt + 1}/{max_retries} to implement solution...")
                
                print("Executing task...")
                self.agent.execute_task(previous_error=self.previous_error)

                print("Running tests...")
                if self.run_tests():
                    print("Tests passed successfully.")
                    return True
                else:
                    print("Tests failed.")
                    print("Test Results:")
                    print(self.get_test_results())
                    self.previous_error = self.test_results  # Store current error for next attempt
                    if attempt < max_retries - 1:
                        print("Retrying with a new implementation...")
                    else:
                        print("Maximum retry attempts reached. Giving up.")
                        return False

        except Exception as e:
            print(f"An error occurred during block execution: {e}")
            return False

    def run_tests(self, test_path: str = None) -> bool:
        """
        Runs the tests using pytest framework.
        Args:
            test_path: Optional path to test file or directory. If None, runs all tests/test*.py files
        """
        try:
            # Default to running all test*.py files in tests directory
            test_target = test_path or 'tests'
            full_path = test_target
            pytest_args = ['--disable-warnings', '-v']

            logger.debug(f"Test target path: {full_path}")
            logger.debug(f"Working directory: {os.getcwd()}")
            
            if os.path.exists(full_path):
                logger.debug(f"Path exists. Is file: {os.path.isfile(full_path)}, Is dir: {os.path.isdir(full_path)}")
            else:
                logger.debug(f"Path does not exist: {full_path}")

            if os.path.isfile(full_path):
                # Single test file case
                logger.debug(f"Running single test file: {test_target}")
                result = self._run_pytest([test_target] + pytest_args)
            elif os.path.isdir(full_path):
                # Directory case - discover and run all test files
                logger.debug(f"Discovering tests in directory: {test_target}")
                test_files = [f for f in os.listdir(full_path) if f.startswith('test_') and f.endswith('.py')]
                logger.debug(f"Found test files: {test_files}")
                # Add pattern to only run test*.py files
                result = self._run_pytest([test_target, '-k', 'test_'] + pytest_args)
            else:
                self.test_results = f"Error: Test path not found: {full_path}"
                logger.error(self.test_results)
                print(self.test_results)
                return False

            # Print test output and summary
            print(self.test_results)
            self._print_test_summary()
            return result
            
        except Exception as e:
            self.test_results = str(e)
            logger.exception("Error running tests")
            print(f"Error running tests: {e}")
            return False

    def _run_pytest(self, args: list) -> bool:
        """Helper method to run pytest with given arguments"""
        try:
            command = ['pytest'] + args
            logger.debug(f"Running pytest command: {' '.join(command)}")
            
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=30  # Add 30 second timeout
            )
            logger.debug(f"Pytest return code: {result.returncode}")
            logger.debug(f"Pytest stdout: {result.stdout}")
            logger.debug(f"Pytest stderr: {result.stderr}")
            
            self.test_results = result.stdout + "\n" + result.stderr
            return result.returncode == 0
        except subprocess.TimeoutExpired as timeout_err:
            # Capture any partial output that was generated before timeout
            partial_output = ""
            if timeout_err.stdout:
                partial_output += "\nPartial stdout before timeout:\n" + timeout_err.stdout.decode('utf-8')
            if timeout_err.stderr:
                partial_output += "\nPartial stderr before timeout:\n" + timeout_err.stderr.decode('utf-8')
            
            error_msg = f"Error: Test discovery/execution timed out after 30 seconds\n{partial_output}"
            logger.error(error_msg)
            self.test_results = error_msg
            print(self.test_results)
            return False
        except subprocess.SubprocessError as e:
            error_msg = f"Error running pytest: {str(e)}"
            logger.error(error_msg)
            self.test_results = error_msg
            print(self.test_results)
            return False

    def _print_test_summary(self):
        """Parse test results and print a colored summary"""
        import re
        from colorama import init, Fore, Style
        init()  # Initialize colorama

        # Look for the test summary line
        summary_match = re.search(r'=+ (.+) in [0-9.]+s =+', self.test_results)
        if not summary_match:
            return

        summary = summary_match.group(1).strip()
        
        # Extract numbers using regex
        numbers = re.findall(r'(\d+) (passed|failed|skipped|error|xfailed|xpassed)', summary)
        if not numbers:
            return

        total = 0
        results = {'passed': 0, 'failed': 0, 'error': 0, 'skipped': 0, 'xfailed': 0, 'xpassed': 0}
        
        # Count the results
        for count, status in numbers:
            count = int(count)
            results[status] = count
            total += count

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
        if results['xfailed'] > 0:
            print(f"{Fore.YELLOW}Expected failures: {results['xfailed']}{Style.RESET_ALL}")
        if results['xpassed'] > 0:
            print(f"{Fore.YELLOW}Unexpected passes: {results['xpassed']}{Style.RESET_ALL}")
        print("="*50)

    def get_test_results(self) -> str:
        return self.test_results
