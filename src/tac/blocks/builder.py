from tac.blocks.model import ProtoBlock
from tac.blocks.generator import ProtoBlockGenerator
from tac.coding_agents import AgentConstructor
from tac.utils.git_manager import GitManager
import git
import sys
import os
from datetime import datetime
from tac.utils.file_gatherer import gather_python_files
from typing import Dict, Optional, Tuple
from tac.core.log_config import setup_logging, get_current_execution_id
from tac.core.config import config
import shutil
from tac.trusty_agents.pytest import PytestTestingAgent, ErrorAnalyzer
from tac.trusty_agents.plausibility import PlausibilityTestingAgent

logger = setup_logging('tac.blocks.builder')

class BlockBuilder:
    """
    Builds a Block from a ProtoBlock by managing the implementation process through an agent,
    running tests, and handling version control operations.
    """
    def __init__(self, config_override: Optional[Dict] = None, codebase: Optional[Dict[str, str]] = None):
        self.protoblock = None
        self.codebase = codebase  # Store codebase internally
        
        # Use the AgentConstructor to create the appropriate agent
        self.agent = AgentConstructor.create_agent(config_override=config_override)
        
        self.test_runner = PytestTestingAgent()
        self.previous_error = None  # Track previous error
        self.git_enabled = config.git.enabled  # Get git enabled status from centralized config
        self.git_manager = GitManager() if self.git_enabled else None
        self.protoblock_id = None 
        self.protoblock_generator = ProtoBlockGenerator()  # Initialize generator
        self.revert_on_failure = False  # Default to not reverting changes on failure
        self.error_analyzer = ErrorAnalyzer()
        self.plausibility_checker = PlausibilityTestingAgent()  # Initialize plausibility checker
        self.initial_test_functions = []  # Store initial test function names
        self.initial_test_count = 0  # Store initial test count
        self.test_results = None

    def execute_block(self, protoblock: ProtoBlock, idx_attempt: int) -> Tuple[bool, Optional[str], str]:
        """
        Executes the block with a unified test-and-implement approach.
        
        Args:
            protoblock: The ProtoBlock to implement
            idx_attempt: The attempt index (0-based)
            
        Returns:
            Tuple containing:
                - bool: True if execution was successful, False otherwise
                - Optional[str]: Failure type description if execution failed, None otherwise
                - str: Error analysis if available, empty string otherwise
        """
        self.protoblock = protoblock
        self.protoblock_id = protoblock.block_id
        try:
            execution_success = False
            analysis = ""  # Initialize as empty string instead of None
            
            try:
                # Log start of task execution
                logger.info(f"Starting task execution (attempt {idx_attempt + 1})")
                
                # Pass the previous attempt's analysis to the agent
                self.agent.run(self.protoblock, previous_analysis=analysis)
                # Ensure no tests/tests/ directory exists
                self._cleanup_nested_tests()
                
                # Log completion of task execution
                logger.info(f"Task execution completed (attempt {idx_attempt + 1})")
                
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
                
                # Log failure with analysis
                logger.error(f"Execution failed (attempt {idx_attempt + 1}): {error_msg}")
                if error_analysis:
                    logger.debug(f"Error analysis: {error_analysis}")
                
                return execution_success, failure_type, error_analysis

            
            # Run tests if pytest is in trusty_agents
            if "pytest" in self.protoblock.trusty_agents:
                logger.info("Running pytest tests (included in trusty_agents)...")
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

                # Only return early if tests failed
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

                    logger.info("Returning early due to test failure, skipping any remaining trusty agents")
                    return execution_success, failure_type, error_analysis
                
                # If we get here, tests passed - continue with other trusty agents
                logger.info("Tests passed, continuing with remaining trusty agents if any")
            else:
                logger.info("Pytest tests skipped (not included in trusty_agents)")

            # Check if plausibility test is in trusty_agents
            if "plausibility" in self.protoblock.trusty_agents:
                logger.info("Running plausibility check (included in trusty_agents)...")
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
            else:
                logger.info("Plausibility check skipped (not included in trusty_agents)")
            
            # If we got here, all required tests passed
            execution_success = True
            logger.info("All trusty agents completed successfully")
            return execution_success, None, ""  # Return empty string instead of None

            
        except KeyboardInterrupt:
            logger.info("\nExecution interrupted by user")
            return False, "Execution interrupted", ""
        except Exception as e:
            logger.error(f"Unexpected error during block execution: {e}")
            return False, "Unexpected error", str(e)

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