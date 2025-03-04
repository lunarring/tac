from typing import Dict, List, Union
import json
from datetime import datetime
import os
import hashlib
import time
from tac.protoblock import ProtoBlock
def validate_protoblock_json(json_content: Union[str, Dict]) -> tuple[bool, str]:
    """
    Validates a protoblock JSON content against the expected structure.
    A protoblock serves as the detailed recipe/blueprint for implementing a change, containing:
    - Task Specification: Outlines the new functionality or fixes
    - Test Specification: Defines tests for the functionality
    - Data Generation: Specifies test data needs
    - Context Files: Lists which code files must be examined/updated
    
    Args:
        json_content: Either a JSON string or parsed dict
        
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
            
        # Check if this is the new versioned format
        if 'versions' in data:
            if not isinstance(data['versions'], list) or not data['versions']:
                return False, "versions must be a non-empty list"
            if 'block_id' not in data:
                return False, "block_id is required in versioned format"
            if 'template_type' not in data:
                return False, "template_type is required in versioned format"
                
            # Validate each version
            for i, version in enumerate(data['versions']):
                valid, error = _validate_version_content(version)
                if not valid:
                    return False, f"Version {i} is invalid: {error}"
            return True, ""
        else:
            # Legacy format - validate as single version
            return _validate_version_content(data)
            
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON format: {str(e)}"
    except Exception as e:
        return False, f"Validation error: {str(e)}"

def _validate_version_content(data: Dict) -> tuple[bool, str]:
    """Helper function to validate a single version's content"""
    # Required top-level keys
    required_keys = ['task', 'test', 'write_files', 'context_files', 'commit_message']
    for key in required_keys:
        if key not in data:
            return False, f"Missing required top-level key: {key}"
    
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
    if not isinstance(data['commit_message'], str) or not data['commit_message'].startswith('TAC:'):
        return False, "commit_message must be a string starting with 'TAC:'"
        
    return True, ""

def save_protoblock(json_content: Union[str, Dict], template_type: str, unique_id: str) -> tuple[str, str]:
    """
    Saves a validated protoblock JSON to a file with unique block ID.
    
    Args:
        json_content: The JSON content to save
        template_type: Type of template (e.g., 'refactor', 'test')
        unique_id: The unique identifier for the block (required)
        
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
    
    # Use the provided unique ID only for filename
    filename = f".tac_protoblock_{unique_id}.json"
    with open(filename, 'w', encoding='utf-8') as f:
        if isinstance(json_content, str):
            f.write(json_content)
        else:
            json.dump(json_content, f, indent=2)
    
    return filename, unique_id 

def load_protoblock_from_json(json_path: str) -> ProtoBlock:
    """Load protoblock definition from a JSON file"""
    with open(json_path, 'r') as f:
        data = json.load(f)
    
    # Handle new versioned format
    if isinstance(data, dict) and 'versions' in data:
        # Get the latest version
        version_data = data['versions'][-1]
        block_id = data['block_id']  # Get ID from versioned format
    else:
        # Handle legacy format
        version_data = data
        # Extract block ID from filename as fallback
        filename = os.path.basename(json_path)
        block_id = filename.replace('.tac_protoblock_', '').replace('.json', '')
    
    task_data = version_data['task']
    test_data = version_data['test']
    
    # Ensure all paths are relative
    write_files = [os.path.relpath(path) if os.path.isabs(path) else path for path in version_data['write_files']]
    context_files = [os.path.relpath(path) if os.path.isabs(path) else path for path in version_data.get('context_files', [])]
    
    return ProtoBlock(
        task_description=task_data['specification'],
        test_specification=test_data['specification'],
        test_data_generation=test_data['data'],
        write_files=write_files,
        context_files=context_files,
        block_id=block_id,
        commit_message=version_data.get('commit_message')
    )