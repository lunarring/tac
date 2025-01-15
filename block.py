from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class Block:
    task_description: str
    test_specification: str
    test_data_generation: str
