import os
import subprocess
from tac.coding_agents.base import Agent
from tac.core.log_config import setup_logging
from tac.utils.file_gatherer import gather_python_files
from tac.blocks import ProtoBlock
from tac.core.llm import LLMClient, Message
import select
import time
import sys
from tac.trusty_agents.registry import TrustyAgentRegistry

logger = setup_logging('tac.coding_agents.native')

class NativeAgent(Agent):
    def __init__(self, config: dict):
        super().__init__(config)
        self.agent_config = config.get('aider', {})
        # Initialize LLM client with strong model for implementation
        self.llm_client = LLMClient(llm_type="strong")
        # Initialize note attribute
        self.note = ""
    
    def process_write_and_context_files(self, protoblock: ProtoBlock) -> tuple[list[str], list[str]]:
        # Deduplicate write_files using a set
        write_files = list(set(protoblock.write_files))
        context_files = list(set(protoblock.context_files))
        
        # Validate and clean file paths
        if isinstance(write_files, str):
            logger.warning("write_files is a string, converting to list")
            write_files = [write_files]
        if isinstance(context_files, str):
            logger.warning("context_files is a string, converting to list")
            context_files = [context_files]
        
        # Filter out non-string values
        write_files = [path for path in write_files if isinstance(path, (str, os.PathLike))]
        context_files = [path for path in context_files if isinstance(path, (str, os.PathLike))]
        
        # Ensure all paths are relative
        write_files = [os.path.relpath(path) if os.path.isabs(path) else path for path in write_files]
        context_files = [os.path.relpath(path) if os.path.isabs(path) else path for path in context_files]
            
        # Filter out context files that don't exist
        valid_context_files = []
        for file_path in context_files:
            if os.path.exists(file_path):
                valid_context_files.append(file_path)
            else:
                logger.warning(f"Context file does not exist and will be excluded: {file_path}")
        context_files = valid_context_files

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

        return write_files, context_files

    def _load_file_contents(self, files: list[str], file_type: str) -> dict[str, str]:
        """Helper method to load file contents into a dictionary.
        
        Args:
            files: List of file paths to load
            file_type: Type of files being loaded ('write' or 'context') for logging
            
        Returns:
            Dictionary mapping file paths to their contents
        """
        file_contents = {}
        for file_path in files:
            try:
                if not os.path.exists(file_path):
                    if file_type == 'write':
                        # For write files that don't exist, use a placeholder
                        file_contents[file_path] = "# This file is empty at the moment."
                        logger.info(f"Write file does not exist, using placeholder: {file_path}")
                        continue
                    else:
                        # For context files, this shouldn't happen as we filter them earlier
                        logger.error(f"Context file does not exist: {file_path}")
                        raise FileNotFoundError(f"File not found: {file_path}")
                
                if not os.path.isfile(file_path):
                    logger.error(f"Path exists but is not a file: {file_path}")
                    raise ValueError(f"Path is not a file: {file_path}")
                    
                with open(file_path, 'r') as f:
                    file_contents[file_path] = f.read()
                logger.debug(f"Successfully read {file_type} file: {file_path}")
            except (IOError, OSError) as e:
                if file_type == 'write':
                    # For write files with errors, use an empty string
                    file_contents[file_path] = ""
                    logger.warning(f"Error reading {file_type} file {file_path}, using empty string: {str(e)}")
                else:
                    logger.error(f"Error reading {file_type} file {file_path}: {str(e)}")
                    raise
        return file_contents

    def _format_files_for_prompt(self, file_contents: dict[str, str], is_context: bool = False) -> str:
        """Format file contents into a prompt string.
        
        Args:
            file_contents: Dictionary mapping file paths to their contents
            is_context: Whether these are context files (adds "do not edit" comment)
            
        Returns:
            Formatted string with file contents using ###FILE: markers
        """
        sections = []
        for file_path, content in file_contents.items():
            section = [f"###FILE: {file_path}"]
            if is_context:
                section.append("# This file is for context only, please do not edit it")
            section.append(content)
            section.append("###END_FILE")
            sections.append("\n".join(section))
        
        return "\n\n".join(sections)

    def _create_implementation_prompt(
        self,
        task_description: str,
        context_files_section: str,
        write_files_section: str,
        coding_agent_prompts: dict = None,
    ) -> str:
        """Create the implementation prompt for the LLM.
        
        Args:
            task_description: Description of the task to implement
            context_files_section: Formatted string of context files
            write_files_section: Formatted string of write files
            coding_agent_prompts: Dictionary of coding agent prompts
            
        Returns:
            Complete formatted prompt string
        """
        prompt = f"""Implement the following functionality:
Task Description: {task_description}

Context Files, please do not edit these files:
{context_files_section}

Write files, these are the ones you need to modify:
{write_files_section}

Make sure your implementation passes the tests, if listed in the context files! If there are tests listed in the write files, then you may have to MODIFY existing test so they are adapted to the new functionality you are adding. 
You edit the code in a minimally invasive way, meaning you only edit the parts of the code that are necessary and don't do any refactoring or other unprompted code changes. Thus leave the code as intact and functional as possible given your task.For each write file, you return the FULL code, nothing else, no further explanation. You can only edit the write files that we have supplied you. The response format is:

###FILE: /path/to/first/file.py
# insert the full code here
###END_FILE

###FILE: /path/to/second/file.py
# insert the full code here
###END_FILE

FOR EXAMPLE:
###FILE: /home/users/git/project/first_file.py
import time
time.sleep(1)
###END_FILE

###FILE: /home/users/git/project/second_file.py
import numpy as np
a = np.random.randn(10, 10)
###END_FILE

Additionally, below, you add a small note to the user about the changes you made, should be maximum three sentences. The format is:

###NOTE:
# insert the note here
###END_NOTE

REMEMBER: change as little as possible and ONLY implement functionality that is listed in the task description."""
        
        # Add coding agent prompts if available
        if coding_agent_prompts and len(coding_agent_prompts) > 0:
            prompt += "\n\nAdditional guidance for implementation:\n"
            for agent_name, agent_prompt in coding_agent_prompts.items():
                prompt += f"\n{agent_name} guidance: {agent_prompt}\n"
        
        return prompt

    def _deparse_llm_response(self, response: str, write_files: list[str]) -> tuple[dict[str, str], str]:
        """Deparse the LLM response into a dictionary of file contents and extract the note.
        
        Args:
            response: The raw response from the LLM
            write_files: List of allowed write file paths to validate against
            
        Returns:
            Tuple containing:
                - Dictionary mapping write file paths to their updated contents
                - String containing the extracted note (or empty string if no note found)
            
        Raises:
            ValueError: If response format is invalid
        """
        updated_write_files = {}
        current_file = None
        current_content = []
        note = ""
        in_note = False
        note_content = []
        
        # Convert write_files to set for faster lookup
        allowed_files = set(write_files)
        
        for line in response.split('\n'):
            # Check for note start marker
            if line.strip() == '###NOTE:':
                in_note = True
                continue
                
            # Check for note end marker
            elif line.strip() == '###END_NOTE':
                if in_note:
                    note = '\n'.join(note_content)
                    in_note = False
                continue
                
            # Collect note content
            if in_note:
                note_content.append(line)
                continue
                
            # Check for file start marker
            if line.startswith('###FILE:'):
                if current_file is not None:
                    # We found a new file start before closing the previous one
                    raise ValueError(f"Invalid response format: Found new file marker '{line}' while still processing '{current_file}'")
                
                file_path = line.replace('###FILE:', '').strip()
                if file_path not in allowed_files:
                    logger.warning(f"Unauthorized file in response will be ignored: {file_path}. Only allowed to modify: {write_files}")
                    current_file = None  # Skip this file's content
                else:
                    current_file = file_path
                    current_content = []
                
            # Check for file end marker
            elif line.strip() == '###END_FILE':
                if current_file is None:
                    continue  # Skip end markers for unauthorized files
                
                if current_file in allowed_files:
                    updated_write_files[current_file] = '\n'.join(current_content)
                current_file = None
                current_content = []
                
            # Content lines
            elif current_file is not None:
                current_content.append(line)
        
        # Check if we have any unclosed markers for allowed files
        if current_file is not None and current_file in allowed_files:
            raise ValueError(f"Invalid response format: Unclosed marker for file {current_file}")
            
        return updated_write_files, note

    def run(self, protoblock: ProtoBlock, previous_analysis: str = None) -> None:
        """
        Executes the native LLM command to implement both tests and functionality simultaneously.
        
        Args:
            protoblock: The ProtoBlock instance containing task details and specifications
            previous_analysis: Optional previous analysis result
        """
        # Store the protoblock as an instance variable for use in execute_task
        self.protoblock = protoblock
        
        task_description = protoblock.task_description
        
        # Process and validate files
        write_files, context_files = self.process_write_and_context_files(protoblock)

        # Load file contents
        write_file_contents = self._load_file_contents(write_files, "write")
        context_file_contents = self._load_file_contents(context_files, "context")

        logger.debug(f"Read {len(write_file_contents)} write files and {len(context_file_contents)} context files")

        # GET HERE TRUST AGENT PROMPTS
        # Filter trusty_agent_prompts for those with "coding_agent" as prompt_target
        coding_agent_prompts = {}
        for agent_name, prompt in protoblock.trusty_agent_prompts.items():
            if TrustyAgentRegistry.get_prompt_target(agent_name) == "coding_agent":
                coding_agent_prompts[agent_name] = prompt
                logger.debug(f"Found coding_agent prompt for {agent_name}")
        
        # Format files for prompt
        context_files_prompt = self._format_files_for_prompt(context_file_contents, is_context=True)
        write_files_prompt = self._format_files_for_prompt(write_file_contents)
        
        # Create the implementation prompt
        prompt = self._create_implementation_prompt(
            task_description,
            context_files_prompt,
            write_files_prompt,
            coding_agent_prompts,
        )
        
        # Create message for LLM
        messages = [Message(role="user", content=prompt)]
        
        # Get completion from LLM
        try:
            response = self.llm_client.chat_completion(messages)
            
        except Exception as e:
            logger.error(f"Error during LLM completion or file writing: {str(e)}")
            raise
        
        # Write response to the target files
        if not response:
            logger.error("No response from LLM")
            raise ValueError("No response from LLM")
        
        # Deparse and validate the response
        updated_write_files, note = self._deparse_llm_response(response, write_files)
        
        # Write the updated contents to files
        for file_path, content in updated_write_files.items():
            with open(file_path, 'w') as f:
                f.write(content)
            logger.info(f"Successfully wrote implementation to {file_path}")
            
        # Store the note as an instance variable
        self.note = note
        
        # Log the note if one was provided
        if note:
            logger.info(f"Note from LLM: {note}")

    def execute_task(self, previous_error: str = None) -> None:
        """Legacy method to maintain compatibility with base Agent class"""
        self.run(self.protoblock, previous_error)
        # The note is now stored as an instance variable and can be accessed via self.note
