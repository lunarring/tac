from tac.coding_agents.base import Agent
from tac.coding_agents.aider import AiderAgent
from tac.coding_agents.native_agent import NativeAgent
from tac.core.config import config
from typing import Optional, Dict
import logging

# Get logger for this module
logger = logging.getLogger('tac.coding_agents.constructor')

class CodingAgentConstructor:
    """
    Constructor class for creating coding agents based on configuration.
    """
    
    @staticmethod
    def create_agent(coding_agent: Optional[str] = None, config_override: Optional[Dict] = None) -> Agent:
        """
        Create and return an agent instance based on the specified type and configuration.
        
        Args:
            coding_agent: The type of agent to create. If None, uses the type from config.
            config_override: Optional configuration overrides.
            
        Returns:
            An instance of the requested Agent subclass.
            
        Raises:
            ValueError: If the agent type is invalid.
        """
        # Use type from config if not explicitly provided
        if coding_agent is None:
            coding_agent = config.general.coding_agent
            logger.debug(f"Using coding agent from config: {coding_agent}")
        else:
            logger.debug(f"Using explicitly provided coding agent: {coding_agent}")
            
        # Prepare configuration
        agent_config = config.raw_config.copy()
        if config_override:
            logger.debug(f"Applying config override: {config_override}")
            agent_config.update(config_override)
            config.override_with_dict(config_override)
        
        # Log the final coding agent type being used
        logger.info(f"Attempting to create coding agent of type: {coding_agent}")
        
        # Create the appropriate agent
        if coding_agent == "aider":
            return AiderAgent(agent_config)
        elif coding_agent == "native":
            return NativeAgent(agent_config)
        else:
            available_agents = ["aider", "native"]
            error_msg = (
                f"Invalid coding agent: '{coding_agent}'. "
                f"Available agents are: {', '.join(available_agents)}. "
                f"Check your configuration or override parameters."
            )
            logger.error(error_msg)
            if config_override and 'general' in config_override and 'coding_agent' in config_override['general']:
                logger.error(f"Config override contains coding_agent: {config_override['general']['coding_agent']}")
            logger.error(f"Current config.general.coding_agent: {config.general.coding_agent}")
            raise ValueError(error_msg) 