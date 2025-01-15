import subprocess
import os
from abc import ABC, abstractmethod

class Agent(ABC):
    def __init__(self, project_dir: str, target_file: str):
        self.project_dir = project_dir
        self.target_file = target_file
        # Ensure tests directory exists
        os.makedirs(os.path.join(project_dir, 'tests'), exist_ok=True)
        # Create __init__.py in tests directory if it doesn't exist
        init_path = os.path.join(project_dir, 'tests', '__init__.py')
        if not os.path.exists(init_path):
            open(init_path, 'w').close()

    @abstractmethod
    def execute_task(self, task_description: str, function_name: str) -> None:
        pass

    @abstractmethod
    def generate_tests(self, test_specification: str, test_data_generation: str, function_name: str) -> None:
        pass

class AiderAgent(Agent):
    def execute_task(self, task_description: str, function_name: str) -> None:
        """
        Executes the Aider command to implement the task.
        """
        prompt = f"Implement the function '{function_name}' according to this specification:\n{task_description}"
        command = [
            'aider',
            '--yes-always',
            '--no-git',
            '--file', self.target_file,
            '--message', prompt
        ]
        try:
            result = subprocess.run(command, check=True, cwd=self.project_dir,
                                    capture_output=True, text=True)
            print("Aider executed successfully.")
            print(result.stdout)
        except subprocess.CalledProcessError as e:
            print(f"Error executing Aider: {e.stderr}")
            raise

    def generate_tests(self, test_specification: str, test_data_generation: str, function_name: str) -> None:
        """
        Generates test cases in tests/test_new_block.py using Aider based on specifications and data.
        """
        prompt = f"Write tests for the function '{function_name}' using pytest with the following specification:\n{test_specification}\nUse the following test data:\n{test_data_generation}. For the import of {function_name}, you can assume it is in {self.target_file}"
        
        command = [
            'aider',
            '--yes-always',
            '--no-git',
            '--file', 'tests/test_new_block.py',
            '--message', prompt
        ]
        
        try:
            result = subprocess.run(command, check=True, cwd=self.project_dir,
                                  capture_output=True, text=True)
            print("Test generation with Aider executed successfully.")
            print(result.stdout)
        except subprocess.CalledProcessError as e:
            print(f"Error generating tests with Aider: {e.stderr}")
            raise
