from tac.blocks.model import ProtoBlock
from tac.blocks.generator import ProtoBlockGenerator
from tac.coding_agents import CodingAgentConstructor
from tac.utils.git_manager import GitManager, FakeGitManager
from tac.utils.filesystem import cleanup_nested_tests
import git
import sys
import os
from datetime import datetime
from tac.utils.file_gatherer import gather_python_files
from typing import Dict, Optional, Tuple
from tac.core.log_config import setup_logging, get_current_execution_id
from tac.core.config import config
import shutil
from tac.trusty_agents.pytest import PytestTestingAgent
from tac.trusty_agents.plausibility import PlausibilityTestingAgent
from tac.trusty_agents.performance import PerformanceTestingAgent
logger = setup_logging('tac.blocks.executor')

class BlockExecutor:
    """
    Executes a ProtoBlock by transforming it into actual code changes plus trust assurances.
    
    Workflow:
    1. Receives a ProtoBlock
    2. Delegates implementation to a coding agent
    3. Delegates trust assurances to trusty agents
    5. Manages Git operations for the changes
    
    Provides error analysis and feedback for failed implementations.
    """
    def __init__(self, config_override: Optional[Dict] = None, codebase: Optional[Dict[str, str]] = None):
        self.protoblock = None
        self.codebase = codebase  # Store codebase internally
        
        # Use the CodingAgentConstructor to create the appropriate coding agent
        self.coding_agent = CodingAgentConstructor.create_agent(config_override=config_override)
        
        # Use the appropriate git manager based on config
        if config.git.enabled:
            self.git_manager = GitManager()
        else:
            self.git_manager = FakeGitManager()
            
        # Error analyzer is now initialized in PytestTestingAgent and accessed via self.test_runner.error_analyzer

        # Initialize trusty agents
        self.trusty_agents = {}
        self.trusty_agents['pytest'] = PytestTestingAgent()
        self.trusty_agents['plausibiltiy'] = PlausibilityTestingAgent()
        # Comment out the PerformanceTestingAgent initialization since it's marked as TBD
        # self.trusty_agents['performance'] = PerformanceTestingAgent() # TBD soon


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

        try:
            # First run the coding agent
            execution_success = False
            analysis = ""  # Initialize as empty string instead of None
            
            try:
                # Log start of task execution
                logger.info(f"Starting coding agent execution (attempt {idx_attempt + 1})")
                
                # Pass the previous attempt's analysis to the coding agent
                self.coding_agent.run(self.protoblock, previous_analysis=analysis)
                
                # Log completion of task execution
                logger.info(f"Coding agent execution completed (attempt {idx_attempt + 1})")
                
            except Exception as e:
                error_msg = f"Error during coding agent execution: {type(e).__name__}: {str(e)}"
                logger.error(error_msg)

                error_analysis= error_msg
                execution_success = False
                failure_type = "Exception during agent execution"
                
                # Log failure with analysis
                logger.error(f"Execution failed (attempt {idx_attempt + 1}): {error_msg}")
                if error_analysis:
                    logger.debug(f"Error analysis: {error_analysis}")
                
                return execution_success, error_analysis, failure_type 


            # Cycle through trusty agents, gather materials first
            code_diff = self.git_manager.get_complete_diff()
            # protoblock decides the tests that are run, but the order is always hardfixed here.
            
            # Run tests if pytest is in trusty_agents
            if "pytest" in self.protoblock.trusty_agents:
                
                # If we get here, tests passed - continue with other trusty agents
                logger.info("Tests passed, continuing with remaining trusty agents if any")
            else:
                logger.info("Pytest tests skipped (not included in trusty_agents)")

            # Check if plausibility test is in trusty_agents
            if "plausibility" in self.protoblock.trusty_agents:
                logger.info("Running plausibility check (included in trusty_agents)...")
                # Get git diff for plausibility check
                plausibility_check_success, final_plausibility_score, error_analysis = self.plausibility_checker.check(self.protoblock, self.codebase,code_diff)
                
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

