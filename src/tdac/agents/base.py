import os
from abc import ABC, abstractmethod

class Agent(ABC):
    def __init__(self, project_dir: str, target_file: str, config: dict):
        self.project_dir = project_dir
        self.target_file = target_file
        self.config = config
        # Ensure tests directory exists
        os.makedirs(os.path.join(project_dir, 'tests'), exist_ok=True)
        # Create __init__.py in tests directory if it doesn't exist
        init_path = os.path.join(project_dir, 'tests', '__init__.py')
        if not os.path.exists(init_path):
            open(init_path, 'w').close()

    @abstractmethod
    def execute_task(self, previous_error: str = None) -> None:
        pass

    @abstractmethod
    def generate_tests(self) -> None:
        pass 