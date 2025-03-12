from abc import ABC, abstractmethod
from typing import Tuple, Optional, Dict, Any, TypeVar, cast, ClassVar
from functools import wraps

from tac.blocks import ProtoBlock
from tac.core.log_config import setup_logging

logger = setup_logging('tac.trusty_agents.base')

class TrustyAgent(ABC):
    """
    Abstract base class for all trusty agents.
    
    All trusty agents must implement the _check_impl method which evaluates
    a protoblock implementation and returns success status, error analysis,
    and failure type.A trusty agent for verification
    
    Class attributes:
        agent_name: Name of the agent for registration (defaults to class name)
        protoblock_prompt: Prompt content for the protoblock genesis prompt
        description: Description of the agent for the protoblock genesis prompt
    """
    
    # Class variables for registration
    agent_name: ClassVar[str] = ""
    protoblock_prompt: ClassVar[str] = ""
    description: ClassVar[str] = ""
    
    @classmethod
    def register(cls):
        """Register this agent with the registry."""
        try:
            from tac.trusty_agents.registry import TrustyAgentRegistry
            
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
                description
            )
            
            logger.info(f"Registered trusty agent: {name}")
        except Exception as e:
            logger.error(f"Error registering trusty agent {cls.__name__}: {e}")
            import traceback
            logger.debug(traceback.format_exc())
    
    def check(self, protoblock: ProtoBlock, codebase: Dict[str, str], code_diff: str) -> Tuple[bool, str, str]:
        """
        Check the implementation against specified criteria.
        This is a wrapper method that enforces the correct return format.
        
        Args:
            protoblock: The ProtoBlock containing task specifications
            codebase: Dictionary mapping file paths to their contents
            code_diff: The git diff showing implemented changes
            
        Returns:
            Tuple containing:
            - bool: Success status (True if check passed, False otherwise)
            - str: Error analysis (empty string if success is True)
            - str: Failure type description (empty string if success is True)
        """
        try:
            # Call the implementation method
            result = self._check_impl(protoblock, codebase, code_diff)
            
            # Validate the result
            if not isinstance(result, tuple) or len(result) != 3:
                logger.error(f"Invalid return format from {self.__class__.__name__}._check_impl: expected tuple of length 3, got {type(result)}")
                return False, f"Internal error: Invalid return format from {self.__class__.__name__}", "Format error"
            
            success, error_analysis, failure_type = result
            
            # Validate success is a boolean
            if not isinstance(success, bool):
                logger.error(f"Invalid success value from {self.__class__.__name__}._check_impl: expected bool, got {type(success)}")
                return False, f"Internal error: Invalid success value from {self.__class__.__name__}", "Format error"
            
            # Validate error_analysis is a string
            if not isinstance(error_analysis, str):
                logger.error(f"Invalid error_analysis from {self.__class__.__name__}._check_impl: expected str, got {type(error_analysis)}")
                error_analysis = str(error_analysis)
            
            # Validate failure_type is a string
            if not isinstance(failure_type, str):
                logger.error(f"Invalid failure_type from {self.__class__.__name__}._check_impl: expected str, got {type(failure_type)}")
                failure_type = str(failure_type)
            
            # Enforce empty strings for error_analysis and failure_type when success is True
            if success:
                if error_analysis:
                    logger.warning(f"{self.__class__.__name__} returned non-empty error_analysis with success=True, forcing to empty string")
                if failure_type:
                    logger.warning(f"{self.__class__.__name__} returned non-empty failure_type with success=True, forcing to empty string")
                return True, "", ""
            
            # Ensure non-empty failure_type when success is False
            if not failure_type:
                logger.warning(f"{self.__class__.__name__} returned empty failure_type with success=False, using default")
                failure_type = f"{self.__class__.__name__} check failed"
            
            return success, error_analysis, failure_type
            
        except Exception as e:
            logger.exception(f"Exception in {self.__class__.__name__}.check: {str(e)}")
            return False, f"Internal error in {self.__class__.__name__}: {str(e)}", f"{self.__class__.__name__} exception"
    
    @abstractmethod
    def _check_impl(self, protoblock: ProtoBlock, codebase: Dict[str, str], code_diff: str) -> Tuple[bool, str, str]:
        """
        Implementation of the check method. This should be overridden by subclasses.
        
        Args:
            protoblock: The ProtoBlock containing task specifications
            codebase: Dictionary mapping file paths to their contents
            code_diff: The git diff showing implemented changes
            
        Returns:
            Tuple containing:
            - bool: Success status (True if check passed, False otherwise)
            - str: Error analysis (empty string if success is True)
            - str: Failure type description (empty string if success is True)
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