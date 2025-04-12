from abc import ABC, abstractmethod
from typing import Tuple, Optional, Dict, Any, TypeVar, cast, ClassVar, Type, Callable, Union
from functools import wraps

from tac.blocks import ProtoBlock
from tac.core.log_config import setup_logging
from tac.agents.trusty.registry import TrustyAgentRegistry
from tac.agents.trusty.results import TrustyAgentResult

logger = setup_logging('tac.trusty_agents.base')

def trusty_agent(name: str, description: str, protoblock_prompt: str, prompt_target: str = "", llm: str = ""):
    """
    Class decorator for registering TrustyAgent subclasses.
    
    This decorator provides a more elegant way to register trusty agents with
    the registry, setting the agent_name, description, protoblock_prompt, and
    prompt_target in one step.
    
    Args:
        name: The name of the agent for registration
        description: Description of the agent for the protoblock genesis prompt
        protoblock_prompt: Prompt content for the protoblock genesis prompt
        prompt_target: Target for the prompt (optional)
        llm: LLM model to use for the agent (optional)
        
    Returns:
        A decorator function that registers the agent class
    """
    def decorator(cls: Type['TrustyAgent']) -> Type['TrustyAgent']:
        cls.agent_name = name
        cls.description = description
        cls.protoblock_prompt = protoblock_prompt
        cls.prompt_target = prompt_target
        cls.llm = llm
        
        # Register the agent
        cls.register()
        
        return cls
    
    return decorator

class TrustyAgent(ABC):
    """
    Abstract base class for all trusty agents.
    
    All trusty agents must implement the _check_impl method which evaluates
    a protoblock implementation and returns a TrustyAgentResult.
    
    Class attributes:
        agent_name: Name of the agent for registration (defaults to class name)
        protoblock_prompt: Prompt content for the protoblock genesis prompt
        description: Description of the agent for the protoblock genesis prompt
        prompt_target: Target for the prompt
        llm: LLM model to use for the agent
    """
    
    # Class variables for registration
    agent_name: ClassVar[str] = ""
    protoblock_prompt: ClassVar[str] = ""
    description: ClassVar[str] = ""
    prompt_target: ClassVar[str] = ""
    llm: ClassVar[str] = ""
    
    @classmethod
    def register(cls):
        """Register this agent with the registry."""
        try:
            if not cls.agent_name:
                # Use class name if agent_name is not set
                name = cls.__name__.lower()
                if name.endswith('agent'):
                    name = name[:-5]  # Remove 'agent' suffix if present
                if name.endswith('testing'):
                    name = name[:-7]  # Remove 'testing' suffix if present
            else:
                name = cls.agent_name
                
            # Default description if not provided
            description = cls.description or f"'{name}': A trusty agent for verification"
            
            # Register with the registry
            TrustyAgentRegistry.register(
                name,
                cls,
                cls.protoblock_prompt,
                description,
                cls.prompt_target
            )
            
            logger.info(f"Registered trusty agent: {name}")
        except Exception as e:
            logger.error(f"Error registering trusty agent {cls.__name__}: {e}")
            import traceback
            logger.debug(traceback.format_exc())
    
    def check(self, protoblock: ProtoBlock, codebase: Dict[str, str], code_diff: str) -> Union[Tuple[bool, str, str], TrustyAgentResult]:
        """
        Check the implementation against specified criteria.
        This is a wrapper method that handles result formatting and error handling.
        
        Args:
            protoblock: The ProtoBlock containing task specifications
            codebase: Dictionary mapping file paths to their contents
            code_diff: The git diff showing implemented changes
            
        Returns:
            Either a legacy tuple or a TrustyAgentResult object:
            - If using the new system: TrustyAgentResult object
            - If using legacy: Tuple containing:
              * bool: Success status (True if check passed, False otherwise)
              * str: Error analysis (empty string if success is True)
              * str: Failure type description (empty string if success is True)
        """
        try:
            # Get agent name for result
            agent_type = self.agent_name or self.__class__.__name__.lower()
            if not agent_type and agent_type.endswith('agent'):
                agent_type = agent_type[:-5]
            
            # Call the implementation method
            result = self._check_impl(protoblock, codebase, code_diff)
            
            # Handle different return types
            if isinstance(result, TrustyAgentResult):
                # Already a TrustyAgentResult, return as is
                return result
            
            # Legacy tuple format
            if not isinstance(result, tuple) or len(result) != 3:
                logger.error(f"Invalid return format from {self.__class__.__name__}._check_impl: expected tuple of length 3, got {type(result)}")
                error_msg = f"Internal error: Invalid return format from {self.__class__.__name__}"
                
                # Create error result
                error_result = TrustyAgentResult(
                    success=False,
                    agent_type=agent_type,
                    summary=f"Check failed: Format error"
                )
                error_result.add_error(error_msg, "Format error")
                return error_result
            
            success, error_analysis, failure_type = result
            
            # Validate success is a boolean
            if not isinstance(success, bool):
                logger.error(f"Invalid success value from {self.__class__.__name__}._check_impl: expected bool, got {type(success)}")
                error_msg = f"Internal error: Invalid success value from {self.__class__.__name__}"
                
                # Create error result
                error_result = TrustyAgentResult(
                    success=False,
                    agent_type=agent_type,
                    summary=f"Check failed: Format error"
                )
                error_result.add_error(error_msg, "Format error")
                return error_result
                
            # Convert legacy result to TrustyAgentResult
            return TrustyAgentResult.from_legacy_result(success, agent_type, error_analysis, failure_type)
            
        except Exception as e:
            logger.exception(f"Exception in {self.__class__.__name__}.check: {str(e)}")
            
            # Create error result
            agent_type = self.agent_name or self.__class__.__name__.lower()
            error_result = TrustyAgentResult(
                success=False,
                agent_type=agent_type,
                summary=f"Check failed: {self.__class__.__name__} exception"
            )
            error_result.add_error(
                message=f"Internal error in {self.__class__.__name__}: {str(e)}",
                error_type=f"{self.__class__.__name__} exception",
                stacktrace=logger.format_exc() if hasattr(logger, 'format_exc') else None
            )
            return error_result
    
    @abstractmethod
    def _check_impl(self, protoblock: ProtoBlock, codebase: Dict[str, str], code_diff: str) -> Union[Tuple[bool, str, str], TrustyAgentResult]:
        """
        Implementation of the check method. This should be overridden by subclasses.
        
        Args:
            protoblock: The ProtoBlock containing task specifications
            codebase: Dictionary mapping file paths to their contents
            code_diff: The git diff showing implemented changes
            
        Returns:
            Either a legacy tuple or a TrustyAgentResult object:
            - If using the new system: TrustyAgentResult object
            - If using legacy: Tuple containing:
              * bool: Success status (True if check passed, False otherwise)
              * str: Error analysis (empty string if success is True)
              * str: Failure type description (empty string if success is True)
        """
        pass 

    @classmethod
    def get_prompt_sections(cls):
        """
        Get the prompt sections for this agent.
        
        By default, this returns a dictionary with a single section named after the agent_name,
        with the protoblock_prompt as its value.
        
        Subclasses can override this method to provide custom prompt sections.
        
        Returns:
            dict: A dictionary mapping section names to their prompt content
        """
        # Get the agent name, defaulting to the lowercase class name if not set
        name = cls.agent_name
        if not name:
            name = cls.__name__.lower()
            if name.endswith('agent'):
                name = name[:-5]  # Remove 'agent' suffix if present
            if name.endswith('testing'):
                name = name[:-7]  # Remove 'testing' suffix if present
                
        # Return a dictionary with a single section named after the agent
        return {
            name: cls.protoblock_prompt
        } 

class ComparativeTrustyAgent(TrustyAgent):
    """Base class for agents that compare states before and after changes."""
    
    def __init__(self):
        super().__init__()
        self.before_state = None
        
    def capture_before_state(self):
        """Capture the initial state before any changes."""
        self.before_state = self._capture_state()
    
    def _check_impl(self, protoblock: ProtoBlock, codebase: str, code_diff: str) -> Union[Tuple[bool, str, str], TrustyAgentResult]:
        """Implementation of the comparative check."""
        try:
            # Get agent name for the result
            agent_type = self.agent_name or self.__class__.__name__.lower()
            if agent_type.endswith('agent'):
                agent_type = agent_type[:-5]
                
            # Verify we have the before state
            if self.before_state is None:
                result = TrustyAgentResult(
                    success=False,
                    agent_type=agent_type,
                    summary="Check failed: Missing before state"
                )
                result.add_error("No initial state captured", "Missing before state")
                return result
            
            # Capture after state
            after_state = self._capture_state()
            
            # Get comparison criteria from protoblock
            criteria = protoblock.trusty_agent_prompts.get(self.agent_name or agent_type, "")
            
            # Compare states
            success, analysis = self._compare_states(self.before_state, after_state, criteria)
            
            if success:
                result = TrustyAgentResult(
                    success=True,
                    agent_type=agent_type,
                    summary="Check passed successfully"
                )
                result.add_report(analysis, "Comparison Analysis")
                return result
            else:
                result = TrustyAgentResult(
                    success=False,
                    agent_type=agent_type,
                    summary="Check failed: Comparison failed"
                )
                result.add_report(analysis, "Comparison Analysis")
                return result
                
        except Exception as e:
            logger.exception(f"Exception in {self.__class__.__name__}._check_impl: {str(e)}")
            agent_type = self.agent_name or self.__class__.__name__.lower()
            result = TrustyAgentResult(
                success=False,
                agent_type=agent_type,
                summary=f"Check failed: {str(e)}"
            )
            result.add_error(str(e), "Comparison error")
            return result
    
    def _capture_state(self) -> Any:
        """Override this to capture the state for comparison."""
        raise NotImplementedError
        
    def _compare_states(self, before: Any, after: Any, criteria: str) -> Tuple[bool, str]:
        """Override this to implement the comparison logic."""
        raise NotImplementedError 