from dataclasses import dataclass
from typing import Dict, Any
from agent import Agent, AiderAgent

@dataclass
class Block:
    def __init__(self, function_name: str, file_path: str, task_description: str, test_specification: str, test_data_generation: str):
        self.function_name = function_name
        self.file_path = file_path
        self.task_description = task_description
        self.test_specification = test_specification
        self.test_data_generation = test_data_generation

    def create_agent(self, project_dir: str) -> 'Agent':
        """Factory method to create an appropriate agent for this block"""
        # For now we're hardcoding AiderAgent, but this could be made configurable
        return AiderAgent(project_dir=project_dir, target_file=self.file_path)
