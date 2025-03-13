from tac.coding_agents.base import Agent
from tac.coding_agents.aider import AiderAgent
from tac.coding_agents.native_agent import NativeAgent
from tac.core.config import config
from typing import Optional, Dict


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
            
        # Prepare configuration
        agent_config = config.raw_config.copy()
        if config_override:
            agent_config.update(config_override)
            config.override_with_dict(config_override)
        
        # Create the appropriate agent
        if coding_agent == "aider":
            return AiderAgent(agent_config)
        elif coding_agent == "native":
            return NativeAgent(agent_config)
        else:
            raise ValueError(f"Invalid coding agent: {coding_agent}") 