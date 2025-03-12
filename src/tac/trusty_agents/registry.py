import logging

logger = logging.getLogger(__name__)

class TrustyAgentRegistry:
    """Registry for all trusty agents in the system."""
    
    _registry = {}
    _protoblock_prompts = {}
    _descriptions = {}
    _prompt_sections = {}
    
    @classmethod
    def register(cls, name, agent_class, protoblock_prompt=None, description=None):
        """Register a trusty agent with the system."""
        cls._registry[name] = agent_class
        cls._protoblock_prompts[name] = protoblock_prompt or ""
        cls._descriptions[name] = description or f"'{name}': A trusty agent for verification"
        
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
    def generate_trusty_agents_prompt_section(cls):
        """Generate the trusty agents section for the protoblock genesis prompt."""
        sections = []
        for name, desc in cls._descriptions.items():
            sections.append(f"    {desc}")
        
        if not sections:
            return "    No trusty agents are currently registered."
        
        return "\n".join(sections)
    
    @classmethod
    def get_prompt_section(cls, section_name):
        """
        Get a prompt section by name from all registered agents.
        
        Args:
            section_name: The name of the prompt section to get
            
        Returns:
            str: The prompt content for the section, or empty string if not found
        """
        # Look for the section in all registered agents
        for agent_name, sections in cls._prompt_sections.items():
            if section_name in sections:
                return sections[section_name]
        
        # Return empty string if section not found
        return ""
        
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
    def generate_agent_sections_for_output_format_explained(cls):
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
            result += f'    "{section_name}": "{escaped_content}",\n'
        
        return result.rstrip(',\n')
    
    @classmethod
    def generate_agent_sections_for_output_format(cls):
        """
        Generate all agent-specific sections for the output_format.
        
        Returns:
            str: JSON-formatted string containing all agent-specific sections
        """
        sections = cls.get_agent_prompt_sections_for_output_format()
        
        if not sections:
            return ""
            
        result = ""
        
        for section_name in sections.keys():
            result += f'    "{section_name}": "...",\n'
        
        return result.rstrip(',\n')
    
    @classmethod
    def debug_prompt_sections(cls):
        """
        Debug method to print all registered prompt sections.
        
        Returns:
            str: A string representation of all registered prompt sections
        """
        result = "Registered prompt sections:\n"
        
        # Print all registered agents
        result += f"\nRegistered agents: {cls.get_all_agents()}\n\n"
        
        # Print all prompt sections
        for agent_name, sections in cls._prompt_sections.items():
            result += f"  Agent: {agent_name}\n"
            for section_name, content in sections.items():
                # Truncate content if it's too long
                content_preview = content[:50] + "..." if len(content) > 50 else content
                result += f"    Section: {section_name} = {content_preview}\n"
        
        if not cls._prompt_sections:
            result += "  No prompt sections registered.\n"
            
        return result 