import os
import subprocess
from tdac.agents.base import Agent
from tdac.core.logging import logger
from tdac.utils.file_gatherer import gather_python_files

class AiderAgent(Agent):
    def __init__(self, project_dir: str, target_file: str, config: dict):
        super().__init__(project_dir, target_file)
        self.agent_config = config.get('agents', {}).get('programming' if self.__class__.__name__ == 'AiderAgent' else 'testing', {})

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
        prompt += f"The implementation must pass these tests:\n{generated_tests}\n. Take a very close look at the tests and implement the function or whatever changes accordingly. It MUST pass all the tests!"
        if previous_error:
            prompt += f"\nThe previous implementation failed with these errors, please fix them:\n{previous_error}"
        prompt += ". Don't make any __init__.py files."
        
        # Append source code if enabled in config
        if self.agent_config.get('include_source_code', False):
            source_code = gather_python_files(self.project_dir)
            prompt += f"\n\nHere is the full source code of the project:\n{source_code}"
        
        logger.debug("Execution prompt for Aider:\n%s", prompt)
        
        command = [
            'aider',
            '--yes-always',
            '--no-git',
            '--model', self.agent_config.get('model', 'o1-mini'),
            '--file', self.target_file,
            '--input-history-file', '/dev/null',
            '--chat-history-file', '/dev/null',
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
        test_file_path = os.path.join(self.project_dir, 'tests', 'test_new_block.py')
        prompt = f"Write tests for the function '{function_name}' using pytest with the following specification:\n{test_specification}\nUse the following test data:\n{test_data_generation}. For the import of {function_name}, you can assume it is in {self.target_file}. Have a close look on this file, maybe it is a class that needs to be instantiated or maybe just a function that needs to be called. Be sure that you are ONLY writing tests in the file tests/test_new_block.py!"
        
        # Append source code if enabled in config
        if self.agent_config.get('include_source_code', False):
            source_code = gather_python_files(self.project_dir)
            prompt += f"\n\nHere is the full source code of the project, possibly including tests that you should try to be consistent with in your formulation of the new tests. Here is the code: \n{source_code}"
        
        logger.debug("Test generation prompt for Aider:\n%s", prompt)
        
        command = [
            'aider',
            '--yes-always',
            '--no-git',
            '--model', self.agent_config.get('model', 'o1-mini'),
            '--file', test_file_path,
            '--input-history-file', '/dev/null',
            '--chat-history-file', '/dev/null',
        ]

        # Add target file if it exists
        # target_file_path = os.path.join(self.project_dir, self.target_file)
        # if os.path.exists(target_file_path):
        #     logger.info(f"Including existing target file in Aider command: {self.target_file}")
        #     command.extend(['--read', self.target_file])

        command.extend(['--message', prompt])
        
        try:
            result = subprocess.run(command, check=True, cwd=self.project_dir,
                                  capture_output=True, text=True)
            print("Test generation with Aider executed successfully.")
            print(result.stdout)
        except subprocess.CalledProcessError as e:
            print(f"Error generating tests with Aider: {e.stderr}")
            raise 