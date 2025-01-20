import os
import subprocess
from tdac.agents.base import Agent
from tdac.core.logging import logger
from tdac.utils.file_gatherer import gather_python_files

class AiderAgent(Agent):
    def __init__(self, config: dict):
        super().__init__(config)
        self.agent_config = config.get('agents', {}).get('programming' if self.__class__.__name__ == 'AiderAgent' else 'testing', {})

    def execute_task(self, previous_error: str = None) -> None:
        """
        Executes the Aider command to implement the task.
        """
        task_description = self.config['task_description']
        write_files = self.config.get('write_files', [])  # Get write files from config
        context_files = [f for f in self.config.get('context_files', []) if f not in write_files]  # Filter out files already in write_files
        
        logger.debug("Files to be written: %s", write_files)
        logger.debug("Context files to be read: %s", context_files)
        
        prompt = f"Implement changes in the code according to this specification:\n{task_description}\n\n"  
        
        prompt += f"The implementation must pass the tests however. Take a very close look at the tests and implement the function or whatever changes accordingly. It MUST pass all the tests!"

        if previous_error:
            prompt += f"\nYou had an attempt of implementing this before, but it FAILED passing the tests! Here are the errors: please fix them:\n{previous_error}"
        prompt += "Also please don't create any __init__.py files."
    
        
        logger.debug("Execution prompt for Aider:\n%s", prompt)
        
        # Find all test files in the tests directory
        test_files = [f for f in os.listdir('tests') 
                     if f.startswith('test_') and f.endswith('.py')]
        
        logger.debug("Found test files: %s", test_files)
        
        command = [
            'aider',
            '--yes-always',
            '--no-git',
            '--model', self.agent_config.get('model'),
            '--input-history-file', '/dev/null',
            '--chat-history-file', '/dev/null',
            '--llm-history-file', '.aider.llm.history'
        ]

        logger.debug("Using Aider model: %s", self.agent_config.get('model'))

        # Add all write files to be edited
        for write_file in write_files:
            command.extend(['--file', write_file])

        # Add all context files to be read
        for context_file in context_files:
            command.extend(['--read', context_file])

        # Add all test files to be read
        if test_files:
            for test_file in test_files:
                command.extend(['--read', os.path.join('tests', test_file)])
        else:
            # If no test files exist, use the default test_new_block.py
            command.extend(['--read', os.path.join('tests', 'test_new_block.py')])

        command.extend(['--message', prompt])
        
        logger.debug("Final Aider command: %s", ' '.join(command))
        
        try:
            result = subprocess.run(command, check=True, text=True,
                                  capture_output=True)
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
        test_files = [f for f in os.listdir('tests') 
                     if f.startswith('test_') and f.endswith('.py')]
        
        test_specification = self.config['test_specification']
        test_data_generation = self.config['test_data_generation']
        task_description = self.config['task_description']
        write_files = self.config.get('write_files', [])  # Get write files for reading
        context_files = [f for f in self.config.get('context_files', []) if f not in write_files]  # Filter out files already in write_files
        
        prompt = f"""Your task is to extend our tests library with one or several new tests for new functionality that we want to build. CRITICALLY, you ADD new test functions BUT NEVER modify any existing test functions code.
        
Here is the description of the new functionality that will be implemented and for which YOU now will write tests: {task_description}
        
The new tests that you should write have the following specification: {test_specification}

Critically, you are closely adhering to using the following DATA for running the tests: {test_data_generation}

Last remarks:
- be as minimalistic as possible, don't implement too many / unncessary tests
- strongly orient yourself with the existing tests, they are a good reference
- try to be minimally invasive in general
- do not ASSUME that some function in the code exists, always verify the code first
- don't forget to only ADD tests and NOT to modify any existing test functions code
- don't write tests that may time out or cause other problems!
- When dealing with longer-running processes (threads, loops, etc.), ensure your tests have a clear exit condition or mock external/time-dependent calls to avoid indefinite hangs"""
    
        logger.debug("Test generation prompt for Aider:\n%s", prompt)
        
        command = [
            'aider',
            '--yes-always',
            '--no-git',
            '--model', self.agent_config.get('model'),
            # '--input-history-file', '/dev/null',
            # '--chat-history-file', '/dev/null'
        ]

        # Add all write files to be read
        for file in write_files:
            command.extend(['--read', file])

        # Add filtered context files to be read
        for file in context_files:
            command.extend(['--read', file])
                
        if test_files:
            # If there are existing test files, include all of them for writing
            for test_file in test_files:
                command.extend(['--file', os.path.join('tests', test_file)])
        else:
            # If no test files exist, use the default test_new_block.py
            test_file_path = os.path.join('tests', 'test_new_block.py')
            command.extend(['--file', test_file_path])

        command.extend(['--message', prompt])
        
        try:
            result = subprocess.run(command, check=True, text=True,
                                  capture_output=True)
            print("Test generation with Aider executed successfully.")
            print(result.stdout)
        except subprocess.CalledProcessError as e:
            print(f"Error generating tests with Aider: {e.stderr}")
            raise 