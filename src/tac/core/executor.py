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
from tac.protoblock import ProtoBlock, ProtoBlockFactory
from tac.agents.base import Agent
from tac.core.git_manager import GitManager
from tac.core.test_runner import TestRunner
import git
import sys
from tac.core.error_analyzer import ErrorAnalyzer
from tac.core.plausibility_check import PlausibilityChecker
from tac.utils.file_gatherer import gather_python_files
from typing import Dict

logger = logging.getLogger(__name__)

class ProtoBlockExecutor:
    """
    Executes a ProtoBlock by managing the implementation process through an agent,
    running tests, and handling version control operations.
    """
    def __init__(self, protoblock: ProtoBlock, config: dict = None, codebase: Dict[str, str] = None):
        self.protoblock = protoblock
        self.config = config if config else self._load_config()
        self.codebase = codebase  # Store codebase internally
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
        self.error_analyzer = ErrorAnalyzer()
        self.plausibility_checker = PlausibilityChecker()  # Initialize plausibility checker
        self.git_enabled = config.get('git', {}).get('enabled', True)  # Get git enabled status
        self.initial_test_functions = []  # Store initial test function names
        self.initial_test_count = 0  # Store initial test count

    def _load_config(self) -> dict:
        """Load configuration from config.yaml"""
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'config.yaml')
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)

    def _write_log_file(self, attempt: int, success: bool, message: str, analysis: str = None) -> dict:
        """
        Write a log file containing the config and executions data.
        
        Args:
            attempt: The current attempt number
            success: Whether the attempt was successful, or None if in progress
            message: Additional message to include in the log
            analysis: Optional error analysis to include
        """
        if not self.protoblock_id:
            logger.warning("No protoblock ID available for logging")
            return None

        log_filename = f".tac_log_{self.protoblock_id}"
        
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

        # Add failure analysis if provided
        if analysis:
            execution_data['failure_analysis'] = analysis

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
            
        return execution_data

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
            
            # Only check git status if git is enabled
            if self.git_enabled:
                # Check git status and get current branch
                status_ok, current_branch = self.git_manager.check_status()
                if not status_ok:
                    return False
            else:
                current_branch = None
                logger.info("Git operations disabled")
                
            # Verify all tests pass before starting
            logger.info("Verifying all tests pass before starting...")
            if not self.run_tests():
                logger.error("Cannot proceed: some tests are failing")
                logger.error("Cannot start implementation: Please fix failing tests first.")
                return False
                
            # Store initial test information after first run
            self.initial_test_functions = self.test_runner.get_test_functions()
            self.initial_test_count = len(self.initial_test_functions)
            logger.info(f"Initial test count: {self.initial_test_count}")
            logger.debug(f"Initial test functions: {self.initial_test_functions}")

            # Only create feature branch if git is enabled and we're on main/master
            block_branch = current_branch
            if self.git_enabled and current_branch in ['main', 'master']:
                block_branch = f"tac_{self.protoblock_id}"
                if not self.git_manager.create_and_checkout_branch(block_branch):
                    logger.error(f"Failed to create branch {block_branch}")
                    return False
                logger.info(f"Created and switched to branch: {block_branch}")
            elif self.git_enabled:
                logger.info(f"Working on existing branch: {current_branch}")
            else:
                logger.info("Git operations disabled - skipping branch creation")

            execution_success = False
            analysis = None
            
            for attempt in range(max_retries):
                logger.info("="*60)
                logger.info(f"Starting attempt {attempt + 1} of {max_retries}")
                logger.info("="*60)
                
                logger.info("Executing task and generating tests simultaneously...")
                try:
                    # Write log before task execution
                    self._write_log_file(attempt + 1, None, "Starting task execution")
                    
                    # Pass the previous attempt's analysis to the agent
                    self.agent.run(self.protoblock, previous_analysis=analysis)
                    
                    # Write log after task execution
                    self._write_log_file(attempt + 1, None, "Task execution completed")
                    
                except Exception as e:
                    error_msg = f"Error during task execution: {type(e).__name__}: {str(e)}"
                    logger.error(error_msg)
                    
                    # Get analysis before writing log
                    analysis = self.error_analyzer.analyze_failure(
                        self.protoblock, 
                        error_msg,
                        self.codebase
                    )
                    
                    # Write failure log with analysis
                    self._write_log_file(attempt + 1, False, error_msg, analysis)
                    
                    # Store error message for next attempt
                    self.previous_error = error_msg
                    
                    if analysis:
                        logger.error("Error Analysis:")
                        logger.error("="*50)
                        logger.error(analysis)
                        logger.error("="*50)
                    
                    if attempt < max_retries - 1:
                        remaining = max_retries - (attempt + 1)
                        logger.info("="*60)
                        logger.info(f"Attempt {attempt + 1} failed. {remaining} attempts remaining.")
                        logger.info("Retrying with a new implementation...")
                        logger.info("="*60)
                        continue
                    else:
                        logger.info("="*60)
                        logger.info("Maximum retry attempts reached.")
                        break

                logger.info("Running tests...")
                # Write log before running tests
                self._write_log_file(attempt + 1, None, "Starting test execution")

                test_results = self.run_tests()
                
                # Assume test results failed
                if not test_results:
                    logger.error("❌ Tests failed.")
                    logger.error("Test Failure Information:")
                    logger.error("="*50)
                    if hasattr(self, 'test_results'):
                        logger.error(self.test_results)
                    else:
                        logger.error("No test results available")
                    logger.error("="*50)
                    
                    # Update protoblock with test results before anything else
                    self.protoblock.test_results = self.test_results if hasattr(self, 'test_results') else None
                    
                    # Get analysis before writing log
                    analysis = self.error_analyzer.analyze_failure(
                        self.protoblock, 
                        self.test_results,
                        self.codebase
                    )
                    
                    # Write failure log with analysis
                    if analysis:
                        self._write_log_file(attempt + 1, False, "Tests failed", analysis)
                        logger.error("Error Analysis:")
                        logger.error("="*50)
                        logger.error(analysis)
                        logger.error("="*50)
                    
                    if attempt < max_retries - 1:
                        remaining = max_retries - (attempt + 1)
                        logger.info("="*60)
                        logger.info(f"Attempt {attempt + 1} failed. {remaining} attempts remaining.")
                        logger.info("Retrying with a new implementation...")
                        logger.info("="*60)
                        continue
                    else:
                        logger.info("="*60)
                        logger.info("Maximum retry attempts reached.")
                        break
                else:
                    logger.info("✅ All tests passed!")
                    
                    # Get git diff for plausibility check
                    git_diff = self.git_manager.get_complete_diff() if self.git_enabled else ""
                    
                    # Only perform plausibility check if enabled in config
                    plausibility_check_enabled = self.config.get('general', {}).get('plausibility_check', False)
                    
                    if plausibility_check_enabled:
                        # Perform plausibility check
                        logger.info("Verifying implementation plausibility...")
                        plausibility_result = self.plausibility_checker.check_implementation(
                            self.protoblock,
                            git_diff
                        )
                        
                        if plausibility_result["correct"]:
                            logger.info("✅ Implementation verified as plausible!")
                            # Update protoblock with test results
                            self.protoblock.test_results = self.test_results
                            # Write success log with test results
                            self._write_log_file(attempt + 1, True, "Tests passed and implementation verified")
                            
                            execution_success = True
                            break
                        else:
                            logger.error("❌ Implementation verification failed!")
                            logger.error("Verification Failure Information:")
                            logger.error("="*50)
                            logger.error(plausibility_result["reasoning"])
                            logger.error("="*50)
                            
                            # Store the plausibility check reasoning as the previous error
                            self.previous_error = plausibility_result["reasoning"]
                            
                            # Write failure log with plausibility check results
                            self._write_log_file(attempt + 1, False, "Implementation verification failed", plausibility_result["reasoning"])
                            
                            if attempt < max_retries - 1:
                                remaining = max_retries - (attempt + 1)
                                logger.info("="*60)
                                logger.info(f"Attempt {attempt + 1} failed plausibility check. {remaining} attempts remaining.")
                                logger.info("Retrying with a new implementation...")
                                logger.info("="*60)
                                continue
                            else:
                                logger.info("="*60)
                                logger.info("Maximum retry attempts reached.")
                                break
                    else:
                        # If plausibility check is disabled, consider the implementation successful after tests pass
                        logger.info("✅ Implementation successful! (Plausibility check disabled)")
                        # Update protoblock with test results
                        self.protoblock.test_results = self.test_results
                        # Write success log with test results
                        self._write_log_file(attempt + 1, True, "Tests passed")
                        
                        execution_success = True
                        break

            # Log appropriate git commands based on execution result and git status
            logger.info("Git Commands:")
            logger.info("="*50)
            if execution_success:
                if self.git_enabled:
                    # Commit all changes with the protoblock's commit message or default message
                    commit_message = self.protoblock.commit_message or "TAC auto commit, message missing"
                    commit_success = self.git_manager.handle_post_execution(
                        {'git': {'auto_push': True}},  # Enable auto-push for successful execution
                        commit_message
                    )
                    if commit_success:
                        logger.info("Changes have been committed and pushed!")
                    else:
                        logger.warning("Warning: Failed to commit/push changes automatically.")
                    
                    # Only show merge instructions if we created a feature branch
                    if current_branch in ['main', 'master']:
                        logger.info("Implementation successful! To merge and push the changes:")
                        logger.info("tac git mergepush")
                        logger.info("Or manually with:")
                        logger.info(f"  git checkout {current_branch} && git merge {block_branch} && git branch -d {block_branch}")
                    else:
                        logger.info("Implementation successful!")
                else:
                    logger.info("Implementation successful! (Git operations disabled)")
            else:
                if self.git_enabled:
                    logger.info("To clean up and restore to main branch:")
                    logger.info("  tac git restore")
                    # Only show alternative manual cleanup if we created a feature branch
                    if current_branch in ['main', 'master']:
                        logger.info("Or manually with:")
                        logger.info(f"  git restore . && git checkout {current_branch} && git clean -fd && git branch -D {block_branch}")
                else:
                    logger.info("Implementation failed. (Git operations disabled)")
            logger.info("="*50)

            return execution_success

        except Exception as e:
            error_msg = f"An error occurred during block execution: {type(e).__name__}: {str(e)}"
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
        try:
            logger.info("Test Execution Details:")
            logger.info("="*50)
            logger.info(f"Test path: {test_path or 'tests/'}")
            logger.info(f"Working directory: {os.getcwd()}")
            logger.info(f"Python path: {sys.path}")
            logger.info("="*50)
            
            success = self.test_runner.run_tests(test_path)
            self.test_results = self.test_runner.get_test_results()
            return success
        except Exception as e:
            error_msg = f"Error during test execution: {type(e).__name__}: {str(e)}"
            logger.error(error_msg)
            self.test_results = error_msg
            return False

    def get_test_results(self) -> str:
        """Get the full test results including output and summary"""
        return self.test_results
