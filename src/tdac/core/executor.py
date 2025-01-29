import os
import subprocess
import yaml
import logging
import json
from datetime import datetime
import pytest
from _pytest.config import Config
from _pytest.terminal import TerminalReporter
from _pytest.capture import CaptureManager
from tdac.protoblock import ProtoBlock, ProtoBlockFactory
from tdac.agents.base import Agent
from tdac.core.git_manager import GitManager
from tdac.core.test_runner import TestRunner
import git
import sys

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
        self.test_runner = TestRunner()
        self.previous_error = None  # Track previous error
        self.git_manager = GitManager()
        self.protoblock_id = protoblock.block_id  # Set ID directly from protoblock
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
            'test_results': self.test_results,  # Store test results only once
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
                
            # Verify all tests pass before starting
            print("\nVerifying all tests pass before starting...")
            if not self.run_tests():
                logger.error("Cannot proceed: some tests are failing on main/master branch")
                print("\nCannot start implementation: Please fix failing tests on main/master branch first.")
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
                    error_msg = f"Error during task execution: {type(e).__name__}: {str(e)}"
                    print(f"\nExecution Error: {error_msg}")
                    logger.error(error_msg)
                    # Write failure log and get execution data
                    execution_data = self._write_log_file(attempt + 1, False, error_msg)
                    
                    # Store error message for next attempt
                    self.previous_error = error_msg
                    
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
                        print(f"Last error: {error_msg}")
                        print("="*60 + "\n")
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
                    print("\n✅ All tests passed!")
                    # Update protoblock with test results
                    self.protoblock.test_results = self.test_results
                    # Write success log with test results
                    self._write_log_file(attempt + 1, True, "Tests passed successfully")
                    
                    # Commit test changes if any
                    commit_message = f"TDAC: Tests passed on attempt {attempt + 1}"
                    if not self.git_manager.handle_post_execution({'git': {'auto_push': False}}, commit_message):
                        logger.warning("Failed to commit changes after successful tests")
                        
                    execution_success = True
                    break
                else:
                    print("\n❌ Tests failed.")
                    # Update protoblock with test results before anything else
                    self.protoblock.test_results = self.test_results
                    
                    # Write failure log with test results
                    self._write_log_file(attempt + 1, False, "Tests failed")
                    
                    # Commit failed test changes
                    commit_message = f"TDAC: Failed test attempt {attempt + 1}"
                    if not self.git_manager.handle_post_execution({'git': {'auto_push': False}}, commit_message):
                        logger.warning("Failed to commit changes after failed tests")
                    
                    # Create next protoblock with test results from previous attempt
                    try:
                        if self.protoblock_id:
                            self.protoblock = self.protoblock_factory.create_next_protoblock_with_test_results(
                                self.protoblock, 
                                self.test_results
                            )
                            print("\nCreated next protoblock with test results from previous attempt.")
                            
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
                        continue
                    else:
                        print("\n" + "="*60)
                        print("Maximum retry attempts reached.")
                        # Commit any remaining changes before cleanup
                        commit_message = f"TDAC: Failed implementation attempt {attempt + 1}"
                        if not self.git_manager.handle_post_execution({'git': {'auto_push': False}}, commit_message):
                            logger.warning("Failed to commit changes after failed attempt")
                        break

            # Print appropriate git commands based on execution result
            print("\nGit Commands:")
            print("="*50)
            if execution_success:
                # Show final test results
                print("\nFinal Test Results:")
                print("="*50)
                print(self.test_results)
                print("="*50)
                
                # Commit all changes with the protoblock's commit message or default message
                commit_message = self.protoblock.commit_message or "TDAC auto commit, message missing"
                commit_success = self.git_manager.handle_post_execution(
                    {'git': {'auto_push': True}},  # Enable auto-push for successful execution
                    commit_message
                )
                if commit_success:
                    print("Changes have been committed and pushed!")
                else:
                    print("Warning: Failed to commit/push changes automatically.")
                
                print("Implementation successful! To merge the changes:")
                print(f"git checkout {original_branch} && git merge {block_branch} && git branch -d {block_branch}")
            else:
                print("To clean up:")
                print(f"  git restore . && git checkout {original_branch} && git clean -fd && git branch -D {block_branch}")
            print("="*50)

            return execution_success

        except Exception as e:
            error_msg = f"An error occurred during block execution: {type(e).__name__}: {str(e)}"
            print(f"\nExecution Error: {error_msg}")
            logger.error(error_msg)
            # Write error log if we have a protoblock ID
            if self.protoblock_id:
                self._write_log_file(0, False, error_msg)
            return False

    def run_tests(self, test_path: str = None) -> bool:
        """
        Runs the tests using pytest framework.
        Args:
            test_path: Optional path to test file or directory. If None, runs all tests/test*.py files
        """
        success = self.test_runner.run_tests(test_path)
        self.test_results = self.test_runner.get_test_results()
        return success

    def get_test_results(self) -> str:
        """Get the full test results including output and summary"""
        return self.test_results
