import os
import subprocess
from tdac.agents.base import Agent
from tdac.core.logging import logger
from tdac.utils.file_gatherer import gather_python_files

class AiderAgent(Agent):
    def __init__(self, project_dir: str, target_file: str, config: dict):
        super().__init__(project_dir, target_file, config)
        self.agent_config = config.get('agents', {}).get('programming' if self.__class__.__name__ == 'AiderAgent' else 'testing', {})

    def execute_task(self, previous_error: str = None) -> None:
        """
        Executes the Aider command to implement the task.
        """
        task_description = self.config['task_description']
        function_name = self.config['function_name']
        
        prompt = f"Implement changes in the code in {self.target_file} according to this specification:\n{task_description}\n\n"  
        
        prompt += f"The implementation must pass the tests however. Take a very close look at the tests and implement the function or whatever changes accordingly. It MUST pass all the tests!"

        if previous_error:
            prompt += f"\nYou had an attempt of implementing this before, but it FAILED passing the tests! Here are the errors: please fix them:\n{previous_error}"
        prompt += "Also please don't create any __init__.py files."
        
        # Append source code if enabled in config
        if self.agent_config.get('include_source_code', False):
            source_code = gather_python_files(self.project_dir)
            prompt += f"\n\nHere is the full source code of the project:\n{source_code}"
        
        logger.debug("Execution prompt for Aider:\n%s", prompt)
        
        # Find all test files in the tests directory
        tests_dir = os.path.join(self.project_dir, 'tests')
        test_files = [f for f in os.listdir(tests_dir) 
                     if f.startswith('test_') and f.endswith('.py')]
        
        command = [
            'aider',
            '--yes-always',
            '--no-git',
            '--model', self.agent_config.get('model'),
            '--file', self.target_file,
            '--input-history-file', '/dev/null',
            '--chat-history-file', '/dev/null'
        ]

        # Add all test files to be read
        if test_files:
            for test_file in test_files:
                command.extend(['--read', os.path.join('tests', test_file)])
        else:
            # If no test files exist, use the default test_new_block.py
            command.extend(['--read', os.path.join('tests', 'test_new_block.py')])

        command.extend(['--message', prompt])
        
        try:
            result = subprocess.run(command, check=True, cwd=self.project_dir,
                                    capture_output=True, text=True)
            print("Aider executed successfully.")
            print(result.stdout)
        except subprocess.CalledProcessError as e:
            print(f"Error executing Aider: {e.stderr}")
            raise

    def generate_tests(self) -> None:
        """
        Generates the necessary test cases for the update in the new block.
        """
        # Find all test files in the tests directory
        tests_dir = os.path.join(self.project_dir, 'tests')
        test_files = [f for f in os.listdir(tests_dir) 
                     if f.startswith('test_') and f.endswith('.py')]
        
        test_specification = self.config['test_specification']
        test_data_generation = self.config['test_data_generation']
        task_description = self.config['task_description']
        
        prompt = f"""Your task is to extend our tests library with one or several new tests for new functionality that we want to build. CRITICALLY, you ADD new test functions BUT NEVER modify any existing test functions code.
        
        Here briefly a description of the new functionality for which we want to write tests: {task_description}.
        
        The new tests that you should write have the following specification: {test_specification}.
        Critically, you are closely adhering to using the following DATA for running the tests: {test_data_generation}.
        """
        
        # Append source code if enabled in config
        if self.agent_config.get('include_source_code', False):
            source_code = gather_python_files(self.project_dir)
            prompt += f"\n\nHere is the full source code of the project, possibly including tests that you should try to be consistent with in your formulation of the new tests. Here is the code: \n{source_code}"
        
        logger.debug("Test generation prompt for Aider:\n%s", prompt)
        
        command = [
            'aider',
            '--yes-always',
            '--no-git',
            '--model', self.agent_config.get('model'),
            '--input-history-file', '/dev/null',
            '--chat-history-file', '/dev/null',
            '--read', self.target_file
        ]
                
        if test_files:
            # If there are existing test files, include all of them
            for test_file in test_files:
                command.extend(['--file', os.path.join('tests', test_file)])
        else:
            # If no test files exist, use the default test_new_block.py
            test_file_path = os.path.join('tests', 'test_new_block.py')
            command.extend(['--file', test_file_path])

        command.extend(['--message', prompt])
        
        try:
            result = subprocess.run(command, check=True, cwd=self.project_dir,
                                  capture_output=True, text=True)
            print("Test generation with Aider executed successfully.")
            print(result.stdout)
        except subprocess.CalledProcessError as e:
            print(f"Error generating tests with Aider: {e.stderr}")
            raise 