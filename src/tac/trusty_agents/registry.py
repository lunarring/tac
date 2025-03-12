import logging

logger = logging.getLogger(__name__)

class TrustyAgentRegistry:
    """Registry for all trusty agents in the system."""
    
    _registry = {}
    _protoblock_prompts = {}
    _descriptions = {}
    _prompt_sections = {}
    _prompt_targets = {}
    
    @classmethod
    def register(cls, name, agent_class, protoblock_prompt=None, description=None, prompt_target=None):
        """Register a trusty agent with the system."""
        cls._registry[name] = agent_class
        cls._protoblock_prompts[name] = protoblock_prompt or ""
        cls._descriptions[name] = description or f"'{name}': A trusty agent for verification"
        cls._prompt_targets[name] = prompt_target or ""
        
        # Register any prompt sections defined by the agent
        if hasattr(agent_class, "get_prompt_sections") and callable(getattr(agent_class, "get_prompt_sections")):
            try:
                cls._prompt_sections[name] = agent_class.get_prompt_sections()
            except Exception as e:
                logger.error(f"Error getting prompt sections for {name}: {e}")
        
        logger.info(f"Registered trusty agent: {name}")
    
    @classmethod
    def get_agent(cls, name):
        """Get an agent class by name."""
        return cls._registry.get(name)
    
    @classmethod
    def get_protoblock_prompt(cls, name):
        """Get the protoblock prompt for an agent."""
        return cls._protoblock_prompts.get(name, "")
    
    @classmethod
    def get_prompt_target(cls, name):
        """Get the prompt target for an agent."""
        return cls._prompt_targets.get(name, "")
    
    @classmethod
    def get_all_agents(cls):
        """Get a list of all registered agent names."""
        return list(cls._registry.keys())
    
    @classmethod
    def get_trusty_agents_description(cls):
        """
        Get a dictionary of all registered trusty agents and their descriptions.
        
        Returns:
            dict: A dictionary mapping agent names to their descriptions
        """
        return {name: desc for name, desc in cls._descriptions.items()}

    @classmethod
    def get_agent_prompt_sections_for_output_format(cls):
        """
        Get all agent-specific prompt sections for the output format.
        
        Returns:
            dict: A dictionary mapping section names to their prompt content
        """
        result = {}
        
        # Check if there are any prompt sections registered
        if not cls._prompt_sections:
            return result
        
        # Collect all sections from all agents
        for agent_name, sections in cls._prompt_sections.items():
            for section_name, content in sections.items():
                if section_name not in result:
                    result[section_name] = content
        
        return result
        
    @classmethod
    def generate_agent_prompts(cls):
        """
        Generate all agent-specific sections for the output_format_explained.
        
        Returns:
            str: JSON-formatted string containing all agent-specific sections
        """
        sections = cls.get_agent_prompt_sections_for_output_format()
        
        if not sections:
            return ""
            
        result = ""
        
        for section_name, content in sections.items():
            # Escape any quotes in the content
            escaped_content = content.replace('"', '\\"')
            result += f'"{section_name}": "{escaped_content}",\n'
        
        return result.rstrip(',\n')
