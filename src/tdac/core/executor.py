import os
import subprocess
import yaml
import logging
import json
from datetime import datetime
from tdac.core.protoblock import ProtoBlock
from tdac.agents.base import Agent
from tdac.core.git_manager import GitManager
from tdac.utils.protoblock_reflector import ProtoBlockReflector
from tdac.utils.protoblock_factory import ProtoBlockFactory
import git

logger = logging.getLogger(__name__)

class ProtoBlockExecutor:
    """
    Executes a ProtoBlock by managing the implementation process through an agent,
    running tests, and handling version control operations.
    """
    def __init__(self, protoblock: ProtoBlock, config: dict = None):
        self.protoblock = protoblock
        self.config = config if config else self._load_config()
        # Create agent with combined config
        agent_config = self.config.copy()
        agent_config.update({
            'task_description': self.protoblock.task_description,
            'test_specification': self.protoblock.test_specification,
            'test_data_generation': self.protoblock.test_data_generation,
            'write_files': self.protoblock.write_files,
            'context_files': self.protoblock.context_files
        })
        self.agent = protoblock.create_agent(agent_config)
        self.test_results = ""
        self.previous_error = None  # Track previous error
        self.git_manager = GitManager()
        self.protoblock_id = protoblock.block_id  # Set ID directly from protoblock
        self.reflector = ProtoBlockReflector()  # Initialize reflector
        self.protoblock_factory = ProtoBlockFactory()  # Initialize factory
        self.revert_on_failure = False  # Default to not reverting changes on failure

    def _load_config(self) -> dict:
        """Load configuration from config.yaml"""
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'config.yaml')
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)

    def _write_log_file(self, attempt: int, success: bool, message: str) -> dict:
        """
        Write a log file containing the config and executions data.
        The log file structure is:
        {
            "config": {...},  # Global config
            "executions": [   # List of execution attempts
                {
                    "protoblock": {...},
                    "timestamp": "...",
                    "attempt": N,
                    "success": bool,
                    "git_diff": "...",
                    "test_results": "..."
                }
            ]
        }
        
        Args:
            attempt: The current attempt number
            success: Whether the attempt was successful, or None if in progress
            message: Additional message to include in the log
        """
        if not self.protoblock_id:
            logger.warning("No protoblock ID available for logging")
            return None

        log_filename = f".tdac_log_{self.protoblock_id}"
        
        # Get git diff using GitManager's new method
        git_diff = self.git_manager.get_complete_diff()

        # Prepare execution data for this attempt
        execution_data = {
            'protoblock': {
                'task_description': self.protoblock.task_description,
                'test_specification': self.protoblock.test_specification,
                'test_data_generation': self.protoblock.test_data_generation,
                'write_files': self.protoblock.write_files,
                'context_files': self.protoblock.context_files,
                'commit_message': self.protoblock.commit_message
            },
            'timestamp': datetime.now().isoformat(),
            'attempt': attempt,
            'success': success,
            'git_diff': git_diff,
            'test_results': self.test_results,
            'message': message
        }

        try:
            # Load existing log data if it exists
            if os.path.exists(log_filename):
                with open(log_filename, 'r', encoding='utf-8') as f:
                    log_data = json.load(f)
            else:
                # Initialize new log data with config and executions
                log_data = {
                    'config': self.config,
                    'executions': []
                }
            
            # Append new execution data
            if 'executions' not in log_data:
                log_data['executions'] = []
            log_data['executions'].append(execution_data)

            # Write updated log file
            with open(log_filename, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to write log file: {e}")
            
        return execution_data  # Return the data for potential error analysis

    def execute_block(self) -> bool:
        """
        Executes the block with a unified test-and-implement approach.
        Returns:
            bool: True if execution was successful, False otherwise
        """
        try:
            # Get max_retries from config, default to 3 if not found
            max_retries = self.config.get('general', {}).get('max_retries', 3)
            logger.info(f"Using max_retries={max_retries} from config")
            
            # Check git status and get current branch
            status_ok, original_branch = self.git_manager.check_status()
            if not status_ok:
                return False
                
            # Verify we're on main/master branch
            if original_branch not in ['main', 'master']:
                logger.error(f"Must be on main or master branch to create feature branch. Currently on: {original_branch}")
                print("\nPlease switch to main/master branch first:")
                print("  git checkout main")
                return False
                
            # Create and checkout new branch for block execution
            block_branch = f"tdac_{self.protoblock_id}"
            if not self.git_manager.create_and_checkout_branch(block_branch):
                logger.error(f"Failed to create branch {block_branch}")
                return False
                
            logger.info(f"Created and switched to branch: {block_branch}")
            execution_success = False
            
            for attempt in range(max_retries):
                print("\n" + "="*60)
                print(f"Starting attempt {attempt + 1} of {max_retries}")
                print("="*60 + "\n")
                
                print("Executing task and generating tests simultaneously...")
                try:
                    # Write log before task execution
                    self._write_log_file(attempt + 1, None, "Starting task execution")
                    
                    self.agent.run(self.protoblock)
                    
                    # Write log after task execution
                    self._write_log_file(attempt + 1, None, "Task execution completed")
                    
                    # Commit changes after successful implementation
                    commit_message = f"TDAC: Implementation attempt {attempt + 1}"
                    if not self.git_manager.handle_post_execution({'git': {'auto_push': False}}, commit_message):
                        logger.warning("Failed to commit changes after implementation")
                    
                except Exception as e:
                    print(f"Error during task execution: {e}")
                    # Write failure log and get execution data
                    execution_data = self._write_log_file(attempt + 1, False, f"Task execution failed: {str(e)}")
                    
                    # Analyze failure if we have execution data
                    if execution_data:
                        analysis, _ = self.reflector.analyze_and_update(execution_data)
                        print("\nFailure Analysis:")
                        print("="*50)
                        print(analysis)
                        print("="*50)
                        self.previous_error = analysis
                        
                    if attempt < max_retries - 1:
                        remaining = max_retries - (attempt + 1)
                        print("\n" + "="*60)
                        print(f"Attempt {attempt + 1} failed. {remaining} attempts remaining.")
                        print("Retrying with a new implementation...")
                        print("="*60 + "\n")
                        continue
                    else:
                        print("\n" + "="*60)
                        print("Maximum retry attempts reached.")
                        # Commit any remaining changes before cleanup
                        commit_message = f"TDAC: Failed implementation attempt {attempt + 1}"
                        if not self.git_manager.handle_post_execution({'git': {'auto_push': False}}, commit_message):
                            logger.warning("Failed to commit changes after failed attempt")
                        # Write final failure log
                        self._write_log_file(attempt + 1, False, "Maximum retry attempts reached")
                        break

                print("Running tests...")
                # Write log before running tests
                self._write_log_file(attempt + 1, None, "Starting test execution")
                
                if self.run_tests():
                    print("Protoblock could successfully be turned into Mergeblock.")
                    # Write success log
                    self._write_log_file(attempt + 1, True, "Tests passed successfully")
                    
                    # Commit test changes if any
                    commit_message = f"TDAC: Tests passed on attempt {attempt + 1}"
                    if not self.git_manager.handle_post_execution({'git': {'auto_push': False}}, commit_message):
                        logger.warning("Failed to commit changes after successful tests")
                        
                    execution_success = True
                    break
                else:
                    print("Tests failed.")
                    print("Test Results:")
                    print(self.get_test_results())
                    
                    # Commit failed test changes
                    commit_message = f"TDAC: Failed test attempt {attempt + 1}"
                    if not self.git_manager.handle_post_execution({'git': {'auto_push': False}}, commit_message):
                        logger.warning("Failed to commit changes after failed tests")
                    
                    # Update current protoblock with test results before creating next one
                    self.protoblock.test_results = self.test_results
                    
                    # Create next protoblock with test results from previous attempt
                    try:
                        if self.protoblock_id:
                            self.protoblock = self.protoblock_factory.create_next_protoblock_with_test_results(
                                self.protoblock, 
                                self.test_results
                            )
                            print("\nCreated next protoblock with test results from previous attempt.")
                            # Write log for protoblock update
                            self._write_log_file(attempt + 1, None, "Created next protoblock with test results")
                            
                            # Commit the updated protoblock file
                            protoblock_file = f".tdac_protoblock_{self.protoblock_id}.json"
                            if os.path.exists(protoblock_file):
                                commit_message = f"TDAC: Update protoblock with test results from attempt {attempt + 1}"
                                if not self.git_manager.handle_post_execution({'git': {'auto_push': False}}, commit_message):
                                    logger.warning("Failed to commit updated protoblock file")
                        else:
                            logger.error("Cannot create next protoblock: no protoblock ID available")
                    except Exception as e:
                        logger.error(f"Failed to create next protoblock: {e}")
                        # Write log for protoblock creation failure
                        self._write_log_file(attempt + 1, False, f"Failed to create next protoblock: {str(e)}")
                    
                    if attempt < max_retries - 1:
                        remaining = max_retries - (attempt + 1)
                        print("\n" + "="*60)
                        print(f"Attempt {attempt + 1} failed. {remaining} attempts remaining.")
                        print("Retrying with a new implementation...")
                        print("="*60 + "\n")
                        # Write log before retry
                        self._write_log_file(attempt + 1, None, "Preparing for retry")
                        continue
                    else:
                        print("\n" + "="*60)
                        print("Maximum retry attempts reached.")
                        # Commit any remaining changes before cleanup
                        commit_message = f"TDAC: Failed implementation attempt {attempt + 1}"
                        if not self.git_manager.handle_post_execution({'git': {'auto_push': False}}, commit_message):
                            logger.warning("Failed to commit changes after failed attempt")
                        # Write final failure log
                        self._write_log_file(attempt + 1, False, "Maximum retry attempts reached")
                        break

            # Print appropriate git commands based on execution result
            print("\nGit Commands:")
            print("="*50)
            if execution_success:
                print("Implementation successful! To merge the changes:")
                print(f"  git checkout {original_branch} && git merge {block_branch}")
                print(f"  git branch -d {block_branch}  # Optional: delete branch after merging")
            else:
                print("To clean up:")
                print(f"  git restore . && git checkout {original_branch} && git branch -D {block_branch}")
            print("="*50)

            return execution_success

        except Exception as e:
            print(f"An error occurred during block execution: {e}")
            # Write error log if we have a protoblock ID
            if self.protoblock_id:
                self._write_log_file(0, False, f"Unexpected error during execution: {str(e)}")
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
                # Remove the restrictive pattern and let pytest discover all tests
                result = self._run_pytest([test_target, '-v'] + pytest_args)
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
