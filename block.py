from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class Block:
    def __init__(self, function_name: str, task_description: str, test_specification: str, test_data_generation: str):
        self.function_name = function_name
        self.task_description = task_description
        self.test_specification = test_specification
        self.test_data_generation = test_data_generation
