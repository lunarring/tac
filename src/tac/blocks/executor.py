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
                
                # No need to check mandatory status here as that's handled in the processor
                # All agents in protoblock.trusty_agents will run
                
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
        run_all = config.general.trusty_agents.run_all_trusty_agents
        all_passed = True
        first_error_analysis = ""
        first_failure_type = ""
        
        for i, agent in enumerate(agents, 1):
            agent_name = agent.__class__.__name__
            logger.info(f"Running trusty agent: {agent_name}", heading=True)
            
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
                result = agent.check(
                    self.protoblock, self.codebase, code_diff
                )
                
                # Handle both legacy tuple format and new TrustyAgentResult format
                if isinstance(result, tuple) and len(result) == 3:
                    success, error_analysis, failure_type = result
                    
                    # Convert legacy result to TrustyAgentResult for uniform handling
                    from tac.agents.trusty.results import TrustyAgentResult
                    agent_result = TrustyAgentResult.from_legacy_result(
                        success, registry_name, error_analysis, failure_type
                    )
                else:
                    # Already a TrustyAgentResult
                    agent_result = result
                    success = agent_result.success
                    error_analysis = ""
                    failure_type = ""
                    
                    # Extract error analysis and failure type from the result if needed
                    if not success:
                        failure_type = agent_result.summary
                        # Get error analysis from reports or error components
                        for component in agent_result.components:
                            if component.component_type == "report":
                                error_analysis = component.content
                                break
                        if not error_analysis:
                            for component in agent_result.components:
                                if component.component_type == "error":
                                    error_analysis = component.message
                                    break
                
                # Store the agent result in the protoblock
                if hasattr(self, 'protoblock') and self.protoblock:
                    if not self.protoblock.trusty_agent_results:
                        self.protoblock.trusty_agent_results = {}
                    
                    # Convert TrustyAgentResult to dictionary for storage
                    result_dict = agent_result.to_dict()
                    
                    # Extract important information for UI display
                    # Build a more UI-friendly representation
                    ui_friendly_result = {
                        'status': 'passed' if agent_result.success else 'failed',
                        'agent_type': agent_result.agent_type,
                        'summary': agent_result.summary
                    }
                    
                    # Add output content from reports
                    report_texts = []
                    for component in agent_result.components:
                        if component.component_type == "report":
                            report_texts.append(component.content)
                    
                    if report_texts:
                        ui_friendly_result['output'] = "\n\n".join(report_texts)
                    elif error_analysis:
                        ui_friendly_result['output'] = error_analysis
                    else:
                        ui_friendly_result['output'] = agent_result.summary
                    
                    # Add screenshots if present
                    screenshot_paths = []
                    for component in agent_result.components:
                        if component.component_type == "screenshot":
                            screenshot_paths.append(component.path)
                    
                    if screenshot_paths:
                        ui_friendly_result['screenshot_paths'] = screenshot_paths
                        ui_friendly_result['screenshot_path'] = screenshot_paths[0]  # For backward compatibility
                    
                    # Add comparison images if present
                    comparison_paths = []
                    for component in agent_result.components:
                        if component.component_type == "comparison":
                            if hasattr(component, 'before_path') and component.before_path:
                                comparison_paths.append(component.before_path)
                            if hasattr(component, 'after_path') and component.after_path:
                                comparison_paths.append(component.after_path)
                            if hasattr(component, 'reference_path') and component.reference_path:
                                comparison_paths.append(component.reference_path)
                    
                    if comparison_paths:
                        ui_friendly_result['comparison_paths'] = comparison_paths
                    
                    # Set image_url for UI display
                    # First check if there's a comparison_path in details (for ThreeJSVisionBeforeAfterAgent)
                    if 'comparison_path' in agent_result.details and agent_result.details['comparison_path']:
                        ui_friendly_result['image_url'] = agent_result.details['comparison_path']
                    # Then try screenshots if available
                    elif screenshot_paths:
                        ui_friendly_result['image_url'] = screenshot_paths[0]
                    # Finally, use the first comparison path if available
                    elif comparison_paths:
                        ui_friendly_result['image_url'] = comparison_paths[0]
                    
                    # Add grade information if present
                    for component in agent_result.components:
                        if component.component_type == "grade":
                            ui_friendly_result['grade'] = component.grade
                            ui_friendly_result['grade_scale'] = component.scale
                            ui_friendly_result['grade_description'] = component.description
                    
                    # Add metrics if present
                    metrics = []
                    for component in agent_result.components:
                        if component.component_type == "metric":
                            metrics.append({
                                'name': component.name,
                                'value': component.value,
                                'unit': component.unit,
                                'threshold': component.threshold if hasattr(component, 'threshold') else None,
                                'passes': component.passes_threshold if hasattr(component, 'passes_threshold') else None
                            })
                    
                    if metrics:
                        ui_friendly_result['metrics'] = metrics
                    
                    # Add any details from the result
                    ui_friendly_result.update(agent_result.details)
                    
                    # Store both the full result and the UI-friendly version
                    self.protoblock.trusty_agent_results[registry_name] = {
                        'full_result': result_dict,
                        **ui_friendly_result  # Merge in the UI-friendly fields
                    }
                    
                    # Log the result we're storing
                    logger.info(f"Stored result for agent {registry_name}: status={'passed' if success else 'failed'}")
                    logger.info(f"  Components: {len(agent_result.components)} components")
                    logger.info(f"  Summary: {agent_result.summary}")
                
                # Send immediate status update after the agent completes
                if not success:
                    logger.error(f"{agent_name} check failed: {failure_type}")
                    
                    # Save the first failure details
                    if all_passed:
                        all_passed = False
                        first_error_analysis = error_analysis
                        first_failure_type = failure_type
                    
                    # If not run_all, return immediately on first failure
                    if not run_all:
                        return False, error_analysis, failure_type
                else:
                    logger.info(f"{agent_name} check passed")
                
            except Exception as e:
                error_msg = f"Error during {agent_name} check: {type(e).__name__}: {str(e)}"
                logger.error(error_msg, exc_info=True)
                
                # Store the error in the protoblock
                if hasattr(self, 'protoblock') and self.protoblock:
                    if not self.protoblock.trusty_agent_results:
                        self.protoblock.trusty_agent_results = {}
                    
                    # Create an error result
                    from tac.agents.trusty.results import TrustyAgentResult
                    error_result = TrustyAgentResult(
                        success=False,
                        agent_type=registry_name,
                        summary=f"Error in {agent_name}: {type(e).__name__}"
                    )
                    error_result.add_error(
                        message=error_msg,
                        error_type=f"{agent_name} exception",
                        stacktrace=logger.format_exc() if hasattr(logger, 'format_exc') else None
                    )
                    
                    # Create UI-friendly representation
                    ui_friendly_result = {
                        'status': 'error',
                        'agent_type': agent_name,
                        'output': error_msg,
                        'summary': f"Error in {agent_name}: {type(e).__name__}"
                    }
                    
                    # Store both the full result and the UI-friendly version
                    self.protoblock.trusty_agent_results[registry_name] = {
                        'full_result': error_result.to_dict(),
                        **ui_friendly_result
                    }
                
                # Save the first failure details
                if all_passed:
                    all_passed = False
                    first_error_analysis = error_msg
                    first_failure_type = f"{agent_name} execution error"
                
                # If not run_all, return immediately on first failure
                if not run_all:
                    return False, error_msg, f"{agent_name} execution error"
                
        # Return overall status after running all agents
        return all_passed, first_error_analysis, first_failure_type

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
        run_all = config.general.trusty_agents.run_all_trusty_agents
        overall_success = True
        first_error_analysis = None
        first_failure_type = ""

        try:
            # Skip the initial status update since we already have "Starting coding agent" from processor
            
            # Prepare and categorize trusty agents
            standard_agents, comparative_agents = self._prepare_trusty_agents()
            
            # Skip the detailed agent summary in favor of a simpler message during verification

            # Capture initial states for comparative agents
            if comparative_agents:
                # Skip capturing state message since it's not one of the three key stages
                self._capture_initial_states(comparative_agents)
            
            # Run the coding agent
            logger.info(f"Starting coding agent implementation (attempt {idx_attempt + 1})", heading=True)
            try:
                # Skip duplicated status update since it's sent from the processor
                
                # Pass empty string as previous_analysis for first attempt
                self.coding_agent.run(self.protoblock, previous_analysis="")
                
                # Update status immediately after coding agent completes
                logger.info(f"Coding agent implementation completed (attempt {idx_attempt + 1})")
                self.ui_manager.send_status_bar("Coding implementation completed")
            except Exception as e:
                error_msg = f"Error during coding agent execution: {type(e).__name__}: {str(e)}"
                logger.error(error_msg)
                self.ui_manager.send_status_bar(f"Coding agent error: {type(e).__name__}")
                return False, error_msg, "Exception during agent execution"

            # Get the diff for trusty agents
            code_diff = self.git_manager.get_complete_diff()
            
            # Run comparative agents 
            if comparative_agents:
                # This is the third key stage - trusty agents
                self.ui_manager.send_status_bar("Running trusty agents...")
                success, error_analysis, failure_type = self._run_trusty_agents(comparative_agents, code_diff)
                if not success:
                    overall_success = False
                    first_error_analysis = error_analysis
                    first_failure_type = failure_type
                    # If not run_all, return immediately after failure
                    if not run_all:
                        return False, error_analysis, failure_type
                
            # Run standard trusty agents 
            if standard_agents:
                # Skip additional status update for standard agents since we already
                # indicated we're running verification agents above
                success, error_analysis, failure_type = self._run_trusty_agents(standard_agents, code_diff)
                if not success:
                    overall_success = False
                    if not first_error_analysis:  # Only store the first error if we don't have one yet
                        first_error_analysis = error_analysis
                        first_failure_type = failure_type
                    # If not run_all, return immediately after failure
                    if not run_all:
                        return False, error_analysis, failure_type
            
            # Report final status
            if overall_success:
                agent_list = ", ".join(self.protoblock.trusty_agents)
                logger.info(f"All trusty agents are happy ({agent_list}). Trust is assured!", heading=True)
                self.ui_manager.send_status_bar("All verification agents passed")
                return True, None, ""
            else:
                logger.info(f"Some trusty agents failed, but all have run due to run_all_trusty_agents=True", heading=True)
                self.ui_manager.send_status_bar("Some verification agents failed")
                return False, first_failure_type, first_error_analysis
            
        except KeyboardInterrupt:
            logger.info("\nExecution interrupted by user")
            self.ui_manager.send_status_bar("Execution interrupted")
            return False, "Execution interrupted", ""
        except Exception as e:
            logger.error(f"Unexpected error during block execution: {e}", exc_info=True)
            self.ui_manager.send_status_bar(f"Unexpected error: {type(e).__name__}")
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

