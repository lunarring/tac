import subprocess
from test_chain.agents.base import Agent

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