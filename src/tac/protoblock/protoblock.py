from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class ProtoBlock:
    """
    A ProtoBlock represents a task specification that needs to be implemented.
    It contains the task description, test specifications, file information needed
    to implement a change in the codebase, and test results from previous attempts.
    """
    task_description: str
    test_specification: str
    test_data_generation: str
    write_files: list
    context_files: list
    block_id: str
    commit_message: str = None
    branch_name: str = None
    test_results: str = None
