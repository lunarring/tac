from typing import Dict, List, Union
import json
from datetime import datetime
import os
import hashlib
import time

def validate_protoblock_json(json_content: Union[str, Dict]) -> tuple[bool, str]:
    """
    Validates a protoblock JSON content against the expected structure.
    A protoblock serves as the detailed recipe/blueprint for implementing a change, containing:
    - Task Specification: Outlines the new functionality or fixes
    - Test Specification: Defines tests for the functionality
    - Data Generation: Specifies test data needs
    - Context Files: Lists which code files must be examined/updated
    
    Args:
        json_content: Either a JSON string or already parsed dict
        
    Returns:
        tuple[bool, str]: (is_valid, error_message)
    """
    try:
        # Parse JSON if string
        if isinstance(json_content, str):
            # Remove any markdown code fences if present
            cleaned_content = json_content.strip()
            if cleaned_content.startswith("```"):
                lines = cleaned_content.split("\n")
                start_idx = next((i for i, line in enumerate(lines) if line.startswith("```")), 0) + 1
                end_idx = next((i for i, line in enumerate(lines[start_idx:], start_idx) if line.startswith("```")), len(lines))
                cleaned_content = "\n".join(lines[start_idx:end_idx]).strip()
            data = json.loads(cleaned_content)
        else:
            data = json_content
        
        if not isinstance(data, dict):
            return False, "JSON content must be a dictionary"
            
        # Required top-level keys
        required_keys = ['seedblock', 'task', 'test', 'write_files', 'context_files', 'commit_message']
        for key in required_keys:
            if key not in data:
                return False, f"Missing required top-level key: {key}"
        
        # Validate seedblock section
        if not isinstance(data['seedblock'], dict) or 'instructions' not in data['seedblock']:
            return False, "seedblock section must contain 'instructions'"
            
        # Validate task section
        if not isinstance(data['task'], dict) or 'specification' not in data['task']:
            return False, "task section must contain 'specification'"
            
        # Validate test section
        test_section = data['test']
        if not isinstance(test_section, dict):
            return False, "test section must be a dictionary"
        for key in ['specification', 'data', 'replacements']:
            if key not in test_section:
                return False, f"test section missing required key: {key}"
                
        # Validate write_files and context_files
        if not isinstance(data['write_files'], list):
            return False, "write_files must be a list"
        if not isinstance(data['context_files'], list):
            return False, "context_files must be a list"
            
        # Validate commit message
        if not isinstance(data['commit_message'], str) or not data['commit_message'].startswith('TDAC:'):
            return False, "commit_message must be a string starting with 'TDAC:'"
            
        return True, ""
        
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON format: {str(e)}"
    except Exception as e:
        return False, f"Validation error: {str(e)}"

def save_protoblock(json_content: Union[str, Dict], template_type: str, unique_id: str = None) -> tuple[str, str]:
    """
    Saves a validated protoblock JSON to a file with unique block ID.
    
    Args:
        json_content: The JSON content to save
        template_type: Type of template (e.g., 'refactor', 'test')
        unique_id: Optional unique identifier for the block. If not provided, one will be generated.
        
    Returns:
        tuple[str, str]: (absolute path to saved file, block ID)
    """
    # Clean and validate JSON first
    if isinstance(json_content, str):
        # Remove any markdown code fences if present
        cleaned_content = json_content.strip()
        if cleaned_content.startswith("```"):
            lines = cleaned_content.split("\n")
            start_idx = next((i for i, line in enumerate(lines) if line.startswith("```")), 0) + 1
            end_idx = next((i for i, line in enumerate(lines[start_idx:], start_idx) if line.startswith("```")), len(lines))
            cleaned_content = "\n".join(lines[start_idx:end_idx]).strip()
        json_content = cleaned_content
    
    is_valid, error = validate_protoblock_json(json_content)
    if not is_valid:
        raise ValueError(f"Invalid protoblock JSON: {error}")
    
    # Generate block ID if not provided
    block_id = unique_id if unique_id else f"{int(time.time())}_{template_type}"
    
    # Save to file
    filename = f".tdac_protoblock_{template_type}_{block_id}.json"
    with open(filename, 'w', encoding='utf-8') as f:
        if isinstance(json_content, str):
            f.write(json_content)
        else:
            json.dump(json_content, f, indent=2)
    
    return filename, block_id 