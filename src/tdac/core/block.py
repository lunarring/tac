from dataclasses import dataclass
from typing import Dict, Any
from tdac.agents.base import Agent
from tdac.agents.aider_agent import AiderAgent

class Block:
    def __init__(self, task_description: str, test_specification: str, test_data_generation: str, write_files: list, context_files: list):
        self.task_description = task_description
        self.test_specification = test_specification
        self.test_data_generation = test_data_generation
        self.write_files = write_files
        self.context_files = context_files

    def create_agent(self, config: dict):
        """Create an agent for this block based on the config"""
        from tdac.agents.aider_agent import AiderAgent
        
        # Add block-specific parameters to config
        config.update({
            'task_description': self.task_description,
            'test_specification': self.test_specification,
            'test_data_generation': self.test_data_generation,
            'write_files': self.write_files,
            'context_files': self.context_files
        })
        
        return AiderAgent(config)
