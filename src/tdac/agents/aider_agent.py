import os
import subprocess
from tdac.agents.base import Agent
from tdac.core.logging import logger

class AiderAgent(Agent):
    def execute_task(self, task_description: str, function_name: str, previous_error: str = None) -> None:
        """
        Executes the Aider command to implement the task.
        """
        # Read the generated tests
        test_file_path = os.path.join(self.project_dir, 'tests', 'test_new_block.py')
        try:
            with open(test_file_path, 'r') as f:
                generated_tests = f.read()
        except FileNotFoundError:
            logger.warning(f"Test file not found at {test_file_path}")
            generated_tests = "No tests found yet."

        prompt = f"Implement the function '{function_name}' according to this specification:\n{task_description}\n\n"
        prompt += f"The implementation must pass these tests:\n{generated_tests}\n"
        if previous_error:
            prompt += f"\nThe previous implementation failed with these errors, please fix them:\n{previous_error}"
        prompt += ". Don't make any __init__.py files."
        
        logger.debug("Execution prompt for Aider:\n%s", prompt)
        
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
        
        logger.debug("Test generation prompt for Aider:\n%s", prompt)
        
        test_file_path = os.path.join(self.project_dir, 'tests', 'test_new_block.py')
        command = [
            'aider',
            '--yes-always',
            '--no-git',
            '--file', test_file_path,
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