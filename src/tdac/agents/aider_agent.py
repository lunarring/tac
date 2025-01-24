import os
import subprocess
from tdac.agents.base import Agent
from tdac.core.log_config import setup_logger
from tdac.utils.file_gatherer import gather_python_files
import select
import time

logger = setup_logger(__name__)

class AiderAgent(Agent):
    def __init__(self, config: dict):
        super().__init__(config)
        self.agent_config = config.get('aider', {})

    def run(self, protoblock) -> None:
        """
        Executes the Aider command to implement both tests and functionality simultaneously.
        
        Args:
            protoblock: The ProtoBlock instance containing task details and specifications
        """
        task_description = protoblock.task_description
        test_specification = protoblock.test_specification
        test_data_generation = protoblock.test_data_generation
        
        # Deduplicate write_files using a set
        write_files = list(set(protoblock.write_files))
        # Filter out any files that are already in write_files from context_files using sets
        context_files = list(set(f for f in protoblock.context_files if f not in write_files))
        
        # Validate and clean file paths
        if isinstance(write_files, str):
            logger.warning("write_files is a string, converting to list")
            write_files = [write_files]
        if isinstance(context_files, str):
            logger.warning("context_files is a string, converting to list")
            context_files = [context_files]
            
        logger.debug("DEBUG - File Path Analysis:")
        logger.debug(f"write_files type: {type(write_files)}")
        logger.debug(f"write_files content: {write_files}")
        logger.debug(f"context_files type: {type(context_files)}")
        logger.debug(f"context_files content: {context_files}")
        
        # Ensure we have valid file paths
        write_files = [f for f in write_files if isinstance(f, str) and len(f) > 1]
        context_files = [f for f in context_files if isinstance(f, str) and len(f) > 1]
        
        logger.debug("DEBUG - After cleaning:")
        logger.debug(f"Cleaned write_files: {write_files}")
        logger.debug(f"Cleaned context_files: {context_files}")
        
        logger.debug("Files to be written: %s", write_files)
        logger.debug("Context files to be read: %s", context_files)

        prompt = f"""Implement both the functionality AND its tests simultaneously according to these specifications:

Task Description: {task_description}

Test Requirements:
- Test Specification: {test_specification}
- Test Data Requirements: {test_data_generation}

{f'''Previous Test Results (Failed):
{protoblock.test_results}''' if protoblock.test_results else ''}

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

        # Add all context files to be read
        for context_file in context_files:
            command.extend(['--read', context_file])

        command.extend(['--message', prompt])
        
        logger.info("Final Aider command: %s", ' '.join(command))
        
        try:
            logger.info("Executing Aider command...")
            logger.info("Command details:")
            logger.info(f"- Write files: {write_files}")
            logger.info(f"- Context files: {context_files}")
            logger.info(f"- Test files: {test_files}")
            logger.info(f"- Full prompt:\n{prompt}")
            
            # Set timeout values
            TOTAL_TIMEOUT = self.agent_config.get('model_settings', {}).get('timeout', 600)  # Default to 10 minutes if not specified
            READ_TIMEOUT = 1.0   # 1 second read timeout
            
            # Stream output in real-time with timeout handling
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            start_time = time.time()
            last_output_time = start_time
            
            while True:
                # Check if we've exceeded total timeout
                if time.time() - start_time > TOTAL_TIMEOUT:
                    process.kill()
                    raise TimeoutError(f"Aider process exceeded {TOTAL_TIMEOUT} seconds timeout")
                
                # Check if we've had no output for too long (possible hang)
                if time.time() - last_output_time > 30:  # 30 seconds without output
                    process.kill()
                    raise TimeoutError("Aider process appears to be hung - no output for 30 seconds")
                
                # Use select to wait for output with timeout
                reads = [process.stdout, process.stderr]
                ready_reads, _, _ = select.select(reads, [], [], READ_TIMEOUT)
                
                if process.poll() is not None:
                    # Process finished, get any remaining output
                    remaining_stdout, remaining_stderr = process.communicate()
                    if remaining_stdout:
                        logger.debug(f"FINAL STDOUT: {remaining_stdout}")
                    if remaining_stderr:
                        logger.debug(f"FINAL STDERR: {remaining_stderr}")
                    break
                
                # Read from any ready pipes
                for pipe in ready_reads:
                    line = pipe.readline()
                    if line:
                        last_output_time = time.time()
                        if pipe == process.stdout:
                            logger.debug(f"STDOUT: {line.strip()}")
                        else:
                            logger.debug(f"STDERR: {line.strip()}")
            
            if process.returncode != 0:
                raise subprocess.CalledProcessError(process.returncode, command)
                
            logger.info("Aider executed successfully.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Aider execution failed with return code: {e.returncode}")
            logger.error("Command that failed:")
            logger.error(' '.join(command))
            raise

    def execute_task(self, previous_error: str = None) -> None:
        """Legacy method to maintain compatibility with base Agent class"""
        self.run(self.config) 