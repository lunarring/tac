import os
import subprocess
from tac.agents.base import Agent
from tac.core.log_config import setup_logging
from tac.utils.file_gatherer import gather_python_files
from tac.protoblock import ProtoBlock
from tac.core.llm import LLMClient, Message
import select
import time
import sys

logger = setup_logging('tac.agents.native_agent')

class NativeAgent(Agent):
    def __init__(self, config: dict):
        super().__init__(config)
        self.agent_config = config.get('aider', {})

    def run(self, protoblock: ProtoBlock, previous_analysis: str = None) -> None:
        """
        Executes the native o3-mini command to implement both tests and functionality simultaneously.
        
        Args:
            protoblock: The ProtoBlock instance containing task details and specifications
        """
        task_description = protoblock.task_description
        test_specification = protoblock.test_specification
        test_data_generation = protoblock.test_data_generation
        
        # Deduplicate write_files using a set
        write_files = list(set(protoblock.write_files))
        if len(write_files) > 1:
            raise NotImplementedError("Multiple write files are not supported yet")
            
        # Filter out any files that are already in write_files from context_files using sets
        context_files = list(set(f for f in protoblock.context_files if f not in write_files))

        # Validate and clean file paths
        if isinstance(write_files, str):
            logger.warning("write_files is a string, converting to list")
            write_files = [write_files]
        if isinstance(context_files, str):
            logger.warning("context_files is a string, converting to list")
            context_files = [context_files]
            
        # Ensure we have valid file paths and they exist
        write_files = [f for f in write_files if isinstance(f, str) and len(f) > 1]
        context_files = [f for f in context_files if isinstance(f, str) and len(f) > 1]

        # Check file existence for context files only
        for file_path in context_files:
            if not os.path.exists(file_path):
                logger.error(f"Context file does not exist: {file_path}")
                raise FileNotFoundError(f"Context file not found: {file_path}")

        # Create parent directories for write files if they don't exist
        for file_path in write_files:
            directory = os.path.dirname(file_path)
            if directory and not os.path.exists(directory):
                logger.debug(f"Creating directory for write file: {directory}")
                os.makedirs(directory, exist_ok=True)
            if not os.path.exists(file_path):
                logger.debug(f"Write file does not exist, will create: {file_path}")
                # Touch the file to create it
                with open(file_path, 'a'):
                    pass

        # Read contents of write files and context files
        write_file_contents = {}
        context_file_contents = {}

        for file_path in write_files:
            try:
                if not os.path.isfile(file_path):
                    logger.error(f"Path exists but is not a file: {file_path}")
                    raise ValueError(f"Path is not a file: {file_path}")
                    
                with open(file_path, 'r') as f:
                    write_file_contents[file_path] = f.read()
                logger.debug(f"Successfully read write file: {file_path}")
            except (IOError, OSError) as e:
                logger.error(f"Error reading write file {file_path}: {str(e)}")
                raise

        for file_path in context_files:
            try:
                if not os.path.isfile(file_path):
                    logger.error(f"Path exists but is not a file: {file_path}")
                    raise ValueError(f"Path is not a file: {file_path}")
                    
                with open(file_path, 'r') as f:
                    context_file_contents[file_path] = f.read()
                logger.debug(f"Successfully read context file: {file_path}")
            except (IOError, OSError) as e:
                logger.error(f"Error reading context file {file_path}: {str(e)}")
                raise

        logger.debug(f"Read {len(write_file_contents)} write files and {len(context_file_contents)} context files")
        
        # Create formatted context files section
        context_files_section = "\n".join([
            f"File: {file_path}\n{content}\n"
            for file_path, content in context_file_contents.items()
        ])

        # Create formatted write files section
        write_files_section = "\n".join([
            f"File: {file_path}\n{content}\n"
            for file_path, content in write_file_contents.items()
        ])
        
        prompt = f"""Implement the following functionality:
Task Description: {task_description}

Context Files:
{context_files_section}

Now the file that you need to modify is:
{write_files_section}

Make sure your implementation passes the tests! You ONLY return the FULL modified code, nothing else, no further explanation, just the code of {write_files} that I can directly execute! Remember, you are only implementing PYTHON CODE!"""
        
        logger.debug(f"Native Agent Prompt: {prompt}")
        
        # Initialize LLM client with strong model for implementation
        llm_client = LLMClient(strength="strong")
        
        # Create message for LLM
        messages = [Message(role="user", content=prompt)]
        
        # Get completion from LLM
        try:
            response = llm_client.chat_completion(messages)
            logger.debug(f"Received response from LLM")
            
            # Write response to the target file
            write_file = write_files[0]  # We already validated there's only one write file
            with open(write_file, 'w') as f:
                f.write(response)
            logger.info(f"Successfully wrote implementation to {write_file}")
            
        except Exception as e:
            logger.error(f"Error during LLM completion or file writing: {str(e)}")
            raise

    def execute_task(self, previous_error: str = None) -> None:
        """Legacy method to maintain compatibility with base Agent class"""
        self.run(self.config) 
