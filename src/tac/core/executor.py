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
from tac.agents.native_agent import NativeAgent
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
    def __init__(self, config_override: dict = None, codebase: Dict[str, str] = None):
        self.protoblock = None
        self.codebase = codebase  # Store codebase internally
        
        # Create agent with combined config
        agent_config = config.raw_config.copy()
        if config_override:
            agent_config.update(config_override)
            config.override_with_dict(config_override)
            
        # Create agent directly
        if config.general.agent_type == "aider":
            self.agent = AiderAgent(agent_config)
        elif config.general.agent_type == "native":
            self.agent = NativeAgent(agent_config)
        else:
            raise ValueError(f"Invalid agent type: {config.general.agent_type}")
        self.test_runner = TestRunner()
        self.previous_error = None  # Track previous error
        self.git_enabled = config.git.enabled  # Get git enabled status from centralized config
        self.git_manager = GitManager() if self.git_enabled else None
        self.protoblock_id = None 
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

        # With the new logging system, we don't need to write a separate log file
        # The logging is handled by the log_config.py module
        
        # Create execution data for reference
        execution_data = {
            'timestamp': datetime.now().isoformat(),
            'attempt': attempt,
            'success': success,
            'message': message,
            'protoblock': self.protoblock_factory.to_dict(self.protoblock_id),
            'git_diff': self.git_manager.get_diff() if self.git_enabled else "",
            'test_results': self.get_test_results() or "",
        }
        
        if analysis:
            execution_data['failure_analysis'] = analysis
            
        # Log the execution data
        logger.info(f"Execution {attempt}: {'SUCCESS' if success else 'FAILURE'} - {message}")
        
        return execution_data

    def execute_block(self, protoblock: ProtoBlock, idx_attempt: int) -> bool:
        """
        Executes the block with a unified test-and-implement approach.
        Returns:
            bool: True if execution was successful, False otherwise
        """
        self.protoblock = protoblock
        self.protoblock_id = protoblock.block_id
        try:
            execution_success = False
            analysis = ""  # Initialize as empty string instead of None
            
            try:
                # Write log before task execution
                self._write_log_file(idx_attempt + 1, None, "Starting task execution")
                
                # Pass the previous attempt's analysis to the agent
                self.agent.run(self.protoblock, previous_analysis=analysis)
                # Ensure no tests/tests/ directory exists
                self._cleanup_nested_tests()
                
                # Write log after task execution
                self._write_log_file(idx_attempt + 1, None, "Task execution completed")
                
            except Exception as e:
                error_msg = f"Error during task execution: {type(e).__name__}: {str(e)}"
                logger.error(error_msg)
                
                # Get analysis before writing log
                error_analysis = self.error_analyzer.analyze_failure(
                    self.protoblock, 
                    error_msg,
                    self.codebase
                )

                # If run_error_analysis is disabled, set error_analysis to empty string
                if not config.general.run_error_analysis:
                    error_analysis = ""

                execution_success = False
                failure_type = "Exception during agent execution"
                
                # Write failure log with analysis
                self._write_log_file(idx_attempt + 1, False, error_msg, error_analysis)
                
                return execution_success, failure_type, error_analysis

            
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
                failure_type = "Unit tests failed"
                execution_success = False
                error_analysis = ""  # Initialize as empty string instead of "None"
                logger.debug(f"Software test result: NO SUCCESS. Test results: {test_results}")

                if idx_attempt < config.general.max_retries_block - 1:
                    if config.general.run_error_analysis:
                        error_analysis = self.error_analyzer.analyze_failure(
                            self.protoblock, 
                            test_results,
                            self.codebase
                        )
                        logger.debug(f"Error Analysis: {error_analysis}")
                else:
                    logger.debug("Software test result: FAILURE!")

                return execution_success, failure_type, error_analysis

            # Only perform plausibility check if enabled in config
            plausibility_check_enabled = config.general.plausibility_test
            logger.debug(f"Plausibility check enabled: {plausibility_check_enabled}")
            if plausibility_check_enabled:
                logger.info("Running plausibility check...")
                # Get git diff for plausibility check
                git_diff = self.git_manager.get_complete_diff()
                plausibility_check_success, final_plausibility_score, error_analysis = self.plausibility_checker.check(self.protoblock, git_diff, self.codebase)
                
                # If run_error_analysis is disabled, set error_analysis to empty string
                if not config.general.run_error_analysis:
                    error_analysis = ""
                    
                if not plausibility_check_success:
                    failure_type = "Plausibility check failed"
                    execution_success = False
                    return execution_success, failure_type, error_analysis
                
                else:
                    # If we got here, both tests and plausibility check (if enabled) passed
                    logger.info(f"Plausibility check passed with score: {final_plausibility_score}")
                    execution_success = True
                    return execution_success, None, ""  # Return empty string instead of None
            else:
                logger.debug("Plausibility check disabled")
                execution_success = True
                return execution_success, None, ""  # Return empty string instead of None

            
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
            test_path: Path to test file or directory. Defaults to config.general.test_path
        """
        try:
            test_path = test_path or config.general.test_path
            logger.info("Test Execution Details:")
            logger.info("="*50)
            logger.info(f"Test path: {test_path}")
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
