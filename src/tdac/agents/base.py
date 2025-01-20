import os
from abc import ABC, abstractmethod

class Agent(ABC):
    def __init__(self, config: dict):
        self.config = config
        # Ensure tests directory exists
        os.makedirs('tests', exist_ok=True)
        # Create __init__.py in tests directory if it doesn't exist
        init_path = os.path.join('tests', '__init__.py')
        if not os.path.exists(init_path):
            open(init_path, 'w').close()

    @abstractmethod
    def execute_task(self, previous_error: str = None) -> None:
        pass 