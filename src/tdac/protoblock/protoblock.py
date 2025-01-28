from dataclasses import dataclass
from typing import Dict, Any

class ProtoBlock:
    """
    A ProtoBlock represents a task specification that needs to be implemented.
    It contains the task description, test specifications, file information needed
    to implement a change in the codebase, and test results from previous attempts.
    """
    def __init__(self, task_description: str, test_specification: str, test_data_generation: str,
                 write_files: list, context_files: list, block_id: str, commit_message: str = None,
                 test_results: str = None):
        self.task_description = task_description
        self.test_specification = test_specification
        self.test_data_generation = test_data_generation
        self.write_files = write_files
        self.context_files = context_files
        self.block_id = block_id
        self.commit_message = commit_message or f"TDAC:{block_id} Implementation"
        self.test_results = test_results

    def create_agent(self, config: dict):
        """Create a unified agent for this block based on the config"""
        from tdac.agents.aider_agent import AiderAgent
        
        # Add block-specific parameters to config
        config.update({
            'task_description': self.task_description,
            'test_specification': self.test_specification,
            'test_data_generation': self.test_data_generation,
            'write_files': self.write_files,
            'context_files': self.context_files,
            'block_id': self.block_id
        })
        
        return AiderAgent(config) 