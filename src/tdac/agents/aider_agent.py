import os
import subprocess
from tdac.agents.base import Agent
from tdac.core.logging import logger
from tdac.utils.file_gatherer import gather_python_files

class AiderAgent(Agent):
    def __init__(self, config: dict):
        super().__init__(config)
        self.agent_config = config.get('agents', {}).get('programming', {})

    def execute_task(self, previous_error: str = None) -> None:
        """
        Executes the Aider command to implement both tests and functionality simultaneously.
        """
        task_description = self.config['task_description']
        test_specification = self.config['test_specification']
        test_data_generation = self.config['test_data_generation']
        
        # Deduplicate write_files using a set
        write_files = list(set(self.config.get('write_files', [])))
        # Filter out any files that are already in write_files from context_files using sets
        context_files = list(set(f for f in self.config.get('context_files', []) if f not in write_files))
        
        logger.debug("Files to be written: %s", write_files)
        logger.debug("Context files to be read: %s", context_files)

        if previous_error:
            prompt = f"""Previous attempt failed with these test errors. Please analyze them carefully and fix both the implementation and tests. In a first step clearly think through the problem that occured during testing and why it occured and what could be done to fix it. Without fixing the root issue the problem will occur again, be sure to understand it thoroughly! Also bear in mind that the tests failed with the CURRENT CODE that I have attached, reflecting your previous attempt.
{previous_error}

Original requirements:
Task Description: {task_description}
Test Specification: {test_specification}
Test Data Requirements: {test_data_generation}
Important Guidelines:
- Write both the implementation and corresponding tests
- Ensure tests are CONSISTENT with the code implemented!
- Tests should use the specified test data
- Avoid timeouts in tests
- Don't create __init__.py files
- When dealing with longer-running processes, ensure clear exit conditions
- Tests should be deterministic and reliable"""
        else:
            prompt = f"""Implement both the functionality AND its tests simultaneously according to these specifications:

Task Description: {task_description}

Test Requirements:
- Test Specification: {test_specification}
- Test Data Requirements: {test_data_generation}

Important Guidelines:
- Write both the implementation and corresponding tests
- Ensure tests are CONSISTENT with the code implemented!
- Tests should use the specified test data
- Avoid timeouts in tests
- Don't create __init__.py files
- When dealing with longer-running processes, ensure clear exit conditions
- Tests should be deterministic and reliable"""

        logger.debug("Execution prompt for Aider:\n%s", prompt)
        
        # Find all test files in the tests directory and deduplicate
        test_files = list(set(f for f in os.listdir('tests') 
                     if f.startswith('test_') and f.endswith('.py')))
        
        logger.debug("Found test files: %s", test_files)
        
        command = [
            'aider',
            '--yes-always',
            '--no-git',
            '--model', self.agent_config.get('model'),
            '--input-history-file', '/dev/null',
            '--chat-history-file', '/dev/null',
            '--llm-history-file', '.aider.llm.history_unified'
        ]

        # Add all write files to be edited
        for write_file in write_files:
            command.extend(['--file', write_file])

        # Add test files to be edited
        if test_files:
            for test_file in test_files:
                command.extend(['--file', os.path.join('tests', test_file)])
        else:
            # If no test files exist, create a new one
            command.extend(['--file', os.path.join('tests', 'test_new_block.py')])

        # Add all context files to be read
        for context_file in context_files:
            command.extend(['--read', context_file])

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