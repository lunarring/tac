from typing import Dict, List, Union
import json
from datetime import datetime
import os

def validate_seedblock_json(json_content: Union[str, Dict]) -> tuple[bool, str]:
    """
    Validates a seedblock JSON content against the expected structure.
    
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

def save_seedblock(json_content: Union[str, Dict], template_type: str) -> str:
    """
    Saves a validated seedblock JSON to a file with timestamp.
    
    Args:
        json_content: The JSON content to save
        template_type: Type of template (e.g., 'refactor', 'test')
        
    Returns:
        str: Absolute path to saved file
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
    
    is_valid, error = validate_seedblock_json(json_content)
    if not is_valid:
        raise ValueError(f"Invalid seedblock JSON: {error}")
    
    # Generate filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"seedblock_{template_type}_{timestamp}.json"
    
    # Use absolute path in current directory
    abs_path = os.path.abspath(filename)
    
    # Convert to string if dict
    if isinstance(json_content, dict):
        json_content = json.dumps(json_content, indent=2)
    
    # Save to file
    try:
        with open(abs_path, 'w') as f:
            f.write(json_content)
    except Exception as e:
        raise IOError(f"Failed to save seedblock to {abs_path}: {str(e)}")
    
    return abs_path 