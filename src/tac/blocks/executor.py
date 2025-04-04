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
from tac.utils.ui import NullUIManager
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
    def __init__(self, config_override: Optional[Dict] = None, codebase: Optional[Dict[str, str]] = None, ui_manager=NullUIManager()):
        self.protoblock = None
        self.codebase = codebase  # Store codebase internally
        self.ui_manager = ui_manager
        
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
            agent_name = agent.__class__.__name__
            logger.info(f"Running trusty agent: {agent_name}", heading=True)
            
            # Send status update right before running the agent
            self.ui_manager.send_status_bar(f"Running verification agent: {agent_name}...")
            
            # Get the registry name to use as the key - do this before check() to ensure
            # we have a consistent key for the agent in case of errors
            registry_name = getattr(agent.__class__, 'agent_name', '')
            if not registry_name:
                # Extract name from class name if agent_name not set
                registry_name = agent_name.lower()
                if registry_name.endswith('agent'):
                    registry_name = registry_name[:-5]  # Remove 'agent' suffix
            
            logger.info(f"Using registry name '{registry_name}' for agent {agent_name}")
                
            try:
                # Run the agent check
                success, error_analysis, failure_type = agent.check(
                    self.protoblock, self.codebase, code_diff
                )
                
                # Store the agent result in the protoblock
                if hasattr(self, 'protoblock') and self.protoblock:
                    if not self.protoblock.trusty_agent_results:
                        self.protoblock.trusty_agent_results = {}
                    
                    # Determine the primary output text
                    if not success:
                        output_text = error_analysis
                    else:
                        # Try to use the best available detailed output:
                        # 1. analysis_result from vision agents
                        # 2. detailed_output attribute if it exists
                        # 3. output attribute if it exists
                        # 4. Fall back to a generic "success" message
                        if hasattr(agent, 'analysis_result') and agent.analysis_result:
                            output_text = agent.analysis_result
                        elif hasattr(agent, 'detailed_output') and agent.detailed_output:
                            output_text = agent.detailed_output
                        elif hasattr(agent, 'output') and agent.output:
                            output_text = agent.output
                        else:
                            output_text = 'Verification successful'
                    
                    # Create the base result dictionary
                    result_dict = {
                        'output': output_text,
                        'status': 'passed' if success else 'failed',
                        'agent_type': agent_name
                    }
                    
                    # Add image URLs if they exist
                    if hasattr(agent, 'image_url') and agent.image_url:
                        result_dict['image_url'] = agent.image_url
                    
                    # Add screenshot path if it exists
                    if hasattr(agent, 'screenshot_path') and agent.screenshot_path:
                        result_dict['screenshot_path'] = agent.screenshot_path
                        
                    # Add comparison image if it exists (for vision comparison agents)
                    if hasattr(agent, 'comparison_path') and agent.comparison_path:
                        result_dict['comparison_path'] = agent.comparison_path
                        
                    # Add test results if it's a test runner
                    if hasattr(agent, 'test_results') and agent.test_results:
                        result_dict['test_results'] = agent.test_results
                        
                    # Add summary if it exists
                    if hasattr(agent, 'summary') and agent.summary:
                        result_dict['summary'] = agent.summary
                        
                    # Add plausibility-specific fields if they exist
                    if agent_name.lower() == 'plausibilitytestingagent' or registry_name == 'plausibility':
                        if hasattr(agent, 'grade') and agent.grade:
                            result_dict['grade'] = agent.grade
                        if hasattr(agent, 'grade_info') and agent.grade_info:
                            result_dict['grade_info'] = agent.grade_info
                        if hasattr(agent, 'verification_info') and agent.verification_info:
                            result_dict['verification_info'] = agent.verification_info
                    
                    # Store all available results
                    self.protoblock.trusty_agent_results[registry_name] = result_dict
                    
                    # Log the result we're storing
                    logger.info(f"Stored result for agent {registry_name}: status={result_dict['status']}")
                    logger.info(f"  Output length: {len(output_text)}")
                    for key in result_dict:
                        if key != 'output':  # Skip output as we logged its length above
                            logger.info(f"  {key}: {result_dict[key]}")
                
                # Send immediate status update after the agent completes
                if not success:
                    logger.error(f"{agent_name} check failed: {failure_type}")
                    self.ui_manager.send_status_bar(f"❌ {agent_name} check failed: {failure_type}")
                    return False, error_analysis, failure_type
                else:
                    logger.info(f"{agent_name} check passed")
                    self.ui_manager.send_status_bar(f"✅ {agent_name} check passed")
                    
            except Exception as e:
                error_msg = f"Error during {agent_name} check: {type(e).__name__}: {str(e)}"
                logger.error(error_msg, exc_info=True)
                self.ui_manager.send_status_bar(f"❌ Error in {agent_name}: {type(e).__name__}")
                
                # Store the error in the protoblock
                if hasattr(self, 'protoblock') and self.protoblock:
                    if not self.protoblock.trusty_agent_results:
                        self.protoblock.trusty_agent_results = {}
                    
                    # Store error data
                    self.protoblock.trusty_agent_results[registry_name] = {
                        'output': error_msg,
                        'status': 'error',
                        'agent_type': agent_name
                    }
                    
                    # Log the error result we're storing
                    logger.info(f"Stored error result for agent {registry_name}: status=error")
                
                return False, error_msg, f"Exception in {agent_name} check"
        
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
            # Send initial status update
            self.ui_manager.send_status_bar(f"Preparing to execute protoblock (attempt {idx_attempt + 1})...")
                
            # Prepare and categorize trusty agents
            standard_agents, comparative_agents = self._prepare_trusty_agents()
            
            # Capture initial states for comparative agents
            if comparative_agents:
                self.ui_manager.send_status_bar("Capturing initial state for comparative checks...")
                self._capture_initial_states(comparative_agents)
            
            # Run the coding agent
            logger.info(f"Starting coding agent implementation (attempt {idx_attempt + 1})", heading=True)
            try:
                # Update status right before starting coding agent
                agent_name = config.general.coding_agent
                self.ui_manager.send_status_bar(f"Starting coding agent ({agent_name}) implementation...")
                
                # Pass empty string as previous_analysis for first attempt
                self.coding_agent.run(self.protoblock, previous_analysis="")
                
                # Update status immediately after coding agent completes
                logger.info(f"Coding agent implementation completed (attempt {idx_attempt + 1})")
                self.ui_manager.send_status_bar("Coding implementation completed. Starting verification...")
            except Exception as e:
                error_msg = f"Error during coding agent execution: {type(e).__name__}: {str(e)}"
                logger.error(error_msg)
                self.ui_manager.send_status_bar(f"❌ Coding agent error: {type(e).__name__}")
                return False, error_msg, "Exception during agent execution"

            # Cycle through trusty agents, gather materials first
            self.ui_manager.send_status_bar("Gathering code changes for verification...")
                
            code_diff = self.git_manager.get_complete_diff()
            
            # Run comparative agents 
            if comparative_agents:
                agent_names = ", ".join([a.__class__.__name__ for a in comparative_agents])
                self.ui_manager.send_status_bar(f"Running comparative verification: {agent_names}")
                success, error_analysis, failure_type = self._run_trusty_agents(comparative_agents, code_diff)
                if not success:
                    return False, error_analysis, failure_type
                
            # Run standard trusty agents 
            if standard_agents:
                agent_names = ", ".join([a.__class__.__name__ for a in standard_agents])
                self.ui_manager.send_status_bar(f"Running standard verification: {agent_names}")
                success, error_analysis, failure_type = self._run_trusty_agents(standard_agents, code_diff)
                if not success:
                    return False, error_analysis, failure_type
            
            # If we got here, all agents passed
            agent_list = ", ".join(self.protoblock.trusty_agents)
            logger.info(f"All trusty agents are happy ({agent_list}). Trust is assured!", heading=True)
            self.ui_manager.send_status_bar("✅ All verification agents approved the changes!")
            return True, None, ""
            
        except KeyboardInterrupt:
            logger.info("\nExecution interrupted by user")
            self.ui_manager.send_status_bar("⛔ Execution interrupted by user")
            return False, "Execution interrupted", ""
        except Exception as e:
            logger.error(f"Unexpected error during block execution: {e}", exc_info=True)
            self.ui_manager.send_status_bar(f"❌ Unexpected error: {type(e).__name__}")
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

