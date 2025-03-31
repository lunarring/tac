from tac.blocks.model import ProtoBlock
from tac.blocks.generator import ProtoBlockGenerator
from tac.agents.coding import CodingAgentConstructor
from tac.utils.filesystem import cleanup_nested_tests
from tac.utils.git_manager import create_git_manager
import sys
import os
from datetime import datetime
from tac.utils.file_gatherer import gather_python_files
from typing import Dict, Optional, Tuple, List
from tac.core.log_config import setup_logging, get_current_execution_id
from tac.core.config import config
import shutil
from tac.agents.trusty.registry import TrustyAgentRegistry
from tac.agents.trusty.base import TrustyAgent, ComparativeTrustyAgent
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
        
        # Log configuration information
        logger.info(f"Initializing BlockExecutor with config_override: {config_override}")
        logger.info(f"Current config.general.coding_agent: {config.general.coding_agent}")
        
        try:
            # Use the CodingAgentConstructor to create the appropriate coding agent
            self.coding_agent = CodingAgentConstructor.create_agent(config_override=config_override)
            logger.info(f"Successfully created coding agent of type: {type(self.coding_agent).__name__}")
        except ValueError as e:
            logger.error(f"Failed to create coding agent: {str(e)}")
            # Re-raise the exception to maintain the original behavior
            raise
        
        # Use the appropriate git manager based on config
        self.git_manager = create_git_manager()
            
        # Error analyzer is now initialized in PytestTestingAgent and accessed via self.test_runner.error_analyzer

        # Initialize trusty agents from registry
        self.trusty_agents = {}
        for agent_name in TrustyAgentRegistry.get_all_agents():
            agent_class = TrustyAgentRegistry.get_agent(agent_name)
            if agent_class:
                try:
                    self.trusty_agents[agent_name] = agent_class()
                    logger.info(f"Initialized trusty agent: {agent_name}")
                except Exception as e:
                    logger.error(f"Failed to initialize trusty agent {agent_name}: {str(e)}")

    def _prepare_trusty_agents(self) -> Tuple[List[TrustyAgent], List[TrustyAgent]]:
        """
        Prepare and categorize trusty agents for execution.
        
        Returns:
            Tuple containing:
            - List of standard trusty agents
            - List of comparative trusty agents
        """
        standard_agents = []
        comparative_agents = []
        
        # Sort agents: pytest first, plausibility last, others in between
        sorted_agent_names = []
        
        # Add all other agents except pytest and plausibility
        for agent_name in self.protoblock.trusty_agents:
            if agent_name != "plausibility":
                sorted_agent_names.append(agent_name)
        
        # Add plausibility last
        sorted_agent_names.append("plausibility")
        
        # Categorize agents
        for agent_name in sorted_agent_names:
            if agent_name in self.trusty_agents:
                agent = self.trusty_agents[agent_name]
                if isinstance(agent, ComparativeTrustyAgent):
                    comparative_agents.append(agent)
                else:
                    standard_agents.append(agent)
            else:
                logger.warning(f"Trusty agent '{agent_name}' specified in protoblock but not available in executor")
        
        return standard_agents, comparative_agents

    def _capture_initial_states(self, comparative_agents: List[TrustyAgent]) -> None:
        """
        Capture initial states for all comparative agents.
        
        Args:
            comparative_agents: List of comparative trusty agents
        """
        for agent in comparative_agents:
            try:
                logger.info(f"Capturing initial state for {agent.__class__.__name__}")
                if hasattr(agent, 'set_protoblock'):
                    agent.set_protoblock(self.protoblock)
                agent.capture_before_state()
            except Exception as e:
                logger.error(f"Failed to capture initial state for {agent.__class__.__name__}: {e}")
                raise

    def _run_trusty_agents(self, agents: List[TrustyAgent], code_diff: str) -> Tuple[bool, str, str]:
        """
        Run a list of trusty agents and return the first failure if any.
        
        Args:
            agents: List of trusty agents to run
            code_diff: The git diff showing implemented changes
            
        Returns:
            Tuple containing:
            - bool: Success status
            - str: Error analysis
            - str: Failure type
        """
        for agent in agents:
            logger.info(f"Running trusty agent: {agent.__class__.__name__}", heading=True)
            try:
                success, error_analysis, failure_type = agent.check(
                    self.protoblock, self.codebase, code_diff
                )
                
                if not success:
                    logger.error(f"{agent.__class__.__name__} check failed: {failure_type}")
                    return False, error_analysis, failure_type
                else:
                    logger.info(f"{agent.__class__.__name__} check passed")
                    
            except Exception as e:
                error_msg = f"Error during {agent.__class__.__name__} check: {type(e).__name__}: {str(e)}"
                logger.error(error_msg, exc_info=True)
                return False, error_msg, f"Exception in {agent.__class__.__name__} check"
        
        return True, "", ""

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
            # Prepare and categorize trusty agents
            standard_agents, comparative_agents = self._prepare_trusty_agents()
            
            # Capture initial states for comparative agents
            if comparative_agents:
                self._capture_initial_states(comparative_agents)
            
            # Run the coding agent
            logger.info(f"Starting coding agent implementation (attempt {idx_attempt + 1})", heading=True)
            try:
                # Pass empty string as previous_analysis for first attempt
                self.coding_agent.run(self.protoblock, previous_analysis="")
                logger.info(f"Coding agent implementation completed (attempt {idx_attempt + 1})")
            except Exception as e:
                error_msg = f"Error during coding agent execution: {type(e).__name__}: {str(e)}"
                logger.error(error_msg)
                return False, error_msg, "Exception during agent execution"

            # Cycle through trusty agents, gather materials first
            code_diff = self.git_manager.get_complete_diff()
            
            # Run comparative agents 
            if comparative_agents:
                success, error_analysis, failure_type = self._run_trusty_agents(comparative_agents, code_diff)
                if not success:
                    return False, error_analysis, failure_type
                
            # Run standard trusty agents 
            success, error_analysis, failure_type = self._run_trusty_agents(standard_agents, code_diff)
            if not success:
                return False, error_analysis, failure_type
            
            
            # If we got here, all agents passed
            logger.info(f"All trusty agents are happy ({', '.join(self.protoblock.trusty_agents)}). Trust is assured!", heading=True)
            return True, None, ""
            
        except KeyboardInterrupt:
            logger.info("\nExecution interrupted by user")
            return False, "Execution interrupted", ""
        except Exception as e:
            logger.error(f"Unexpected error during block execution: {e}", exc_info=True)
            return False, str(e), "Unexpected error"

    def run_tests(self, test_path: str = None) -> bool:
        """
        Runs the tests using pytest framework.
        Args:
            test_path: Path to test file or directory. Defaults to config.general.test_path
        """
        try:
            test_path = test_path or config.general.test_path
            logger.info("Test Execution Details:")
            logger.info(f"Test path: {test_path}")
            logger.info(f"Working directory: {os.getcwd()}")
            logger.info(f"Python path: {sys.path}")
            
            success = self.test_runner.run_tests(test_path)
            self.test_results = self.test_runner.get_test_results()
            return success
        except Exception as e:
            error_msg = f"Error during test execution: {type(e).__name__}: {str(e)}"
            logger.error(error_msg)
            self.test_results = error_msg
            return False

