import os
import subprocess
import logging
import json
from datetime import datetime
import pytest
from _pytest.config import Config
from _pytest.terminal import TerminalReporter
from _pytest.capture import CaptureManager
from tac.protoblock import ProtoBlock, ProtoBlockFactory
from tac.agents.base import Agent
from tac.agents.aider_agent import AiderAgent
from tac.core.git_manager import GitManager
from tac.core.test_runner import TestRunner
import git
import sys
from tac.core.error_analyzer import ErrorAnalyzer
from tac.core.plausibility_check import PlausibilityChecker
from tac.utils.file_gatherer import gather_python_files
from typing import Dict
from tac.core.log_config import setup_logging
from tac.core.config import config
import shutil
from tac.utils.log_manager import LogManager

logger = setup_logging('tac.core.executor')

class ProtoBlockExecutor:
    """
    Executes a ProtoBlock by managing the implementation process through an agent,
    running tests, and handling version control operations.
    """
    def __init__(self, protoblock: ProtoBlock, config_override: dict = None, codebase: Dict[str, str] = None):
        self.protoblock = protoblock
        self.codebase = codebase  # Store codebase internally
        
        # Create agent with combined config
        agent_config = config.raw_config.copy()
        if config_override:
            agent_config.update(config_override)
            
        # Create agent directly
        self.agent = AiderAgent(agent_config)
        self.test_runner = TestRunner()
        self.previous_error = None  # Track previous error
        self.git_enabled = config.git.enabled  # Get git enabled status from centralized config
        self.git_manager = GitManager() if self.git_enabled else None
        self.protoblock_id = protoblock.block_id  # Set ID directly from protoblock
        self.protoblock_factory = ProtoBlockFactory()  # Initialize factory
        self.revert_on_failure = False  # Default to not reverting changes on failure
        self.error_analyzer = ErrorAnalyzer()
        self.plausibility_checker = PlausibilityChecker()  # Initialize plausibility checker
        self.initial_test_functions = []  # Store initial test function names
        self.initial_test_count = 0  # Store initial test count
        self.test_results = None
        self.log_manager = LogManager()  # Initialize log manager

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
        
        # Set the log file path in the log manager
        self.log_manager.current_log_path = log_filename
        
        # Get git diff using GitManager's new method if git is enabled
        git_diff = self.git_manager.get_complete_diff() if self.git_manager else ""

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
            'test_results': self.test_results or "",
            'message': message
        }

        # Add failure analysis if provided
        if analysis:
            execution_data['failure_analysis'] = analysis

        # Use the log manager to safely update the log file
        if self.log_manager.safe_update_log(execution_data, config=config.raw_config):
            return execution_data
        else:
            logger.error("Failed to update log file")
            return None

    def _check_nested_tests(self) -> bool:
        """
        Check if tests/tests directory exists, which indicates a potential problem
        from a previous run.
        
        Returns:
            bool: True if nested tests directory exists, False otherwise
        """
        nested_tests_dir = os.path.join('tests', 'tests')
        if os.path.exists(nested_tests_dir):
            logger.error("="*80)
            logger.error("Found nested tests directory (tests/tests/)!")
            logger.error("This usually indicates a problem from a previous run.")
            logger.error("Please move any test files from tests/tests/ to tests/ and remove the nested directory.")
            logger.error("="*80)
            return True
        return False

    def execute_block(self) -> bool:
        """
        Executes the block with a unified test-and-implement approach.
        Returns:
            bool: True if execution was successful, False otherwise
        """
        try:
            # Check for nested tests directory first
            if self._check_nested_tests():
                return False

            # Get max_retries from centralized config
            max_retries = config.general.max_retries
            logger.info(f"Using max_retries={max_retries} from config")
            
            # Handle git branch setup first if git is enabled
            if self.git_enabled:
                current_git_branch = self.git_manager.get_current_branch() or ""
                tac_branch = "tac_" + self.protoblock_id
                
                if current_git_branch.startswith("tac_"):
                    logger.info(f"Already on a TAC branch: {current_git_branch}. No branch switching necessary.")
                    tac_branch = current_git_branch
                else:
                    if not self.git_manager.create_or_switch_to_tac_branch(tac_branch):
                        logger.error(f"Failed to create or switch to TAC branch {tac_branch}")
                        return False
                    logger.info(f"Switched to TAC branch: {tac_branch}")
                    
                # Now check git status, but only for tracked files
                status_ok, _ = self.git_manager.check_status(ignore_untracked=True)
                if not status_ok:
                    return False
            else:
                logger.info("Git operations disabled")
                
            # Store initial test information after first run
            self.initial_test_functions = self.test_runner.get_test_functions()
            self.initial_test_count = len(self.initial_test_functions)
            logger.info(f"Initial test count: {self.initial_test_count}")
            logger.debug(f"Initial test functions: {self.initial_test_functions}")

            execution_success = False
            analysis = None
            
            for attempt in range(max_retries):
                if attempt > 0:
                    # Only show pause prompt if halt_after_fail is true in config
                    if config.general.halt_after_fail:
                        input("Execution paused: press Enter to continue with the next attempt, or Ctrl+C to abort...")

                    # Revert changes on the feature branch if git is enabled
                    if self.git_enabled:
                        logger.info("Reverting changes while staying on feature branch...")
                        self.git_manager.revert_changes()

                logger.info("="*60)
                logger.info(f"🔄 Starting attempt {attempt + 1} of {max_retries}")
                logger.info("="*60)
                
                logger.info("Executing task and generating tests simultaneously...")
                try:
                    # Write log before task execution
                    self._write_log_file(attempt + 1, None, "Starting task execution")
                    
                    # Pass the previous attempt's analysis to the agent
                    self.agent.run(self.protoblock, previous_analysis=analysis)
                    # Ensure no tests/tests/ directory exists
                    self._cleanup_nested_tests()
                    
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
                        logger.debug("Software test result: NO SUCCESS!")
                        continue
                    else:
                        logger.debug("Software test result: SUCCESS!") 
                        return False
                
                # Run tests and get results first
                test_success = self.run_tests()
                test_results = self.test_runner.get_test_results()
                
                # Extract test statistics
                test_stats = self.test_runner.get_test_stats()
                total_tests = sum(test_stats.values()) if test_stats else 0
                failed_tests = test_stats.get('failed', 0) if test_stats else 0
                
                # Log test results
                if failed_tests > 0:
                    logger.warning(f"{failed_tests} out of {total_tests} tests failed")
                    logger.warning("This indicates potential issues but won't stop execution")
                else:
                    logger.info(f"All {total_tests} tests passed successfully")

                # Only consider it a failure if there was an execution error
                # Test failures are warnings but don't stop execution
                if not test_success:
                    logger.debug("Software test result: NO SUCCESS!")
                    if attempt < max_retries - 1:
                        continue
                    else:
                    logger.debug("Software test result: SUCCESS!")
                        return False

                # Only perform plausibility check if enabled in config
                plausibility_check_enabled = config.general.plausibility_test
                logger.debug(f"Plausibility check enabled: {plausibility_check_enabled}")
                if plausibility_check_enabled:
                    logger.info("Running plausibility check...")
                    # Get git diff for plausibility check
                    git_diff = self.git_manager.get_complete_diff()
                    plausibility_check_success = self.plausibility_checker.check(self.protoblock, git_diff)
                    if not plausibility_check_success:
                        logger.error("Plausibility check failed")
                        if attempt < max_retries - 1:
                            continue
                        else:
                            return False
                    else:
                        # If we got here, both tests and plausibility check (if enabled) passed
                        logger.debug("Plausibility check passed")
                        execution_success = True
                        break
                    
                if attempt < max_retries - 1:
                    continue
            
            # Write final log entry
            self._write_log_file(max_retries, execution_success, 
                               "Task completed successfully" if execution_success else "Task failed after all attempts")
            
            # Handle git operations if enabled and execution was successful
            if execution_success and self.git_enabled:
                commit_success = self.git_manager.handle_post_execution(config.raw_config, self.protoblock.commit_message)
                if not commit_success:
                    logger.error("Failed to commit changes")
                    return False
            
            return execution_success
            
        except KeyboardInterrupt:
            logger.info("\nExecution interrupted by user")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during block execution: {e}")
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

    def _cleanup_nested_tests(self):
        """
        Cleanup nested test directory by moving files from tests/tests/ to tests/
        and removing the tests/tests directory if it exists.
        """
        nested_tests_dir = os.path.join('tests', 'tests')
        if not os.path.exists(nested_tests_dir):
            return

        logger.info("Found nested tests directory. Moving files to parent directory...")
        
        try:
            # Move all files from tests/tests to tests
            for item in os.listdir(nested_tests_dir):
                src_path = os.path.join(nested_tests_dir, item)
                dst_path = os.path.join('tests', item)
                
                if os.path.isfile(src_path):
                    # If destination exists, remove it first
                    if os.path.exists(dst_path):
                        os.remove(dst_path)
                        logger.info(f"Removed existing file {item} in tests/")
                    
                    os.rename(src_path, dst_path)
                    logger.info(f"Moved {item} to tests/")
            
            # Force remove the tests/tests directory and all its contents
            shutil.rmtree(nested_tests_dir)
            logger.info("Removed nested tests directory and all its contents")
            
        except Exception as e:
            logger.error(f"Error during test directory cleanup: {str(e)}")
