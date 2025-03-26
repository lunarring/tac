import os
from typing import Dict
from tac.core.log_config import setup_logging

logger = setup_logging('tac.utils.file_utils')

def load_file_contents(files: list[str], file_type: str) -> dict[str, str]:
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

def format_files_for_prompt(file_contents: dict[str, str], is_context: bool = False) -> str:
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