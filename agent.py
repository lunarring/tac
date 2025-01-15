import subprocess
import os
from abc import ABC, abstractmethod

class Agent(ABC):
    @abstractmethod
    def execute_task(self, task_description: str) -> None:
        pass

    @abstractmethod
    def generate_tests(self, test_specification: str, test_data_generation: str) -> None:
        pass

class AiderAgent(Agent):
    def __init__(self, project_dir: str):
        self.project_dir = project_dir

    def execute_task(self, task_description: str) -> None:
        """
        Executes the Aider command to implement the task.
        """
        command = [
            'aider',
            '--yes-always',
            '--no-git',
            '--file', 'main.py',
            '--message', task_description
        ]
        try:
            result = subprocess.run(command, check=True, cwd=self.project_dir,
                                    capture_output=True, text=True)
            print("Aider executed successfully.")
            print(result.stdout)
        except subprocess.CalledProcessError as e:
            print(f"Error executing Aider: {e.stderr}")
            raise

    def generate_tests(self, test_specification: str, test_data_generation: str) -> None:
        """
        Generates test cases in test_main.py using Aider based on specifications and data.
        """
        prompt = f"Write a test using pytest with the following specification: {test_specification}\nUse the following test data: {test_data_generation}"
        
        command = [
            'aider',
            '--yes-always',
            '--no-git',
            '--file', 'test_main.py',
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
