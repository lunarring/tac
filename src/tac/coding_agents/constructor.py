from tac.coding_agents.base import Agent
from tac.coding_agents.aider import AiderAgent
from tac.coding_agents.native_agent import NativeAgent
from tac.core.config import config
from typing import Optional, Dict


class AgentConstructor:
    """
    Constructor class for creating coding agents based on configuration.
    """
    
    @staticmethod
    def create_agent(agent_type: Optional[str] = None, config_override: Optional[Dict] = None) -> Agent:
        """
        Create and return an agent instance based on the specified type and configuration.
        
        Args:
            agent_type: The type of agent to create. If None, uses the type from config.
            config_override: Optional configuration overrides.
            
        Returns:
            An instance of the requested Agent subclass.
            
        Raises:
            ValueError: If the agent type is invalid.
        """
        # Use type from config if not explicitly provided
        if agent_type is None:
            agent_type = config.general.agent_type
            
        # Prepare configuration
        agent_config = config.raw_config.copy()
        if config_override:
            agent_config.update(config_override)
            config.override_with_dict(config_override)
        
        # Create the appropriate agent
        if agent_type == "aider":
            return AiderAgent(agent_config)
        elif agent_type == "native":
            return NativeAgent(agent_config)
        else:
            raise ValueError(f"Invalid agent type: {agent_type}") 