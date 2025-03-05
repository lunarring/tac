from typing import Dict, List, Optional, Union, Tuple
import json
from datetime import datetime
import os
import hashlib
import time
from pathlib import Path

from .model import ProtoBlock
from .factory import ProtoBlockFactory

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
    
    # Use the factory's verification method instead
    factory = ProtoBlockFactory()
    is_valid, error, _ = factory.verify_protoblock(json_content if isinstance(json_content, str) else json.dumps(json_content))
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
    """
    Loads a protoblock from a JSON file.
    
    Args:
        json_path: Path to the JSON file
        
    Returns:
        ProtoBlock: The loaded protoblock
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Parse the JSON content
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {json_path}: {str(e)}")
    
    # Check if this is a versioned format
    if isinstance(data, dict) and 'versions' in data and isinstance(data['versions'], list) and len(data['versions']) > 0:
        # Use the latest version
        version_data = data['versions'][-1]
        block_id = data.get('block_id', os.path.basename(json_path).replace('.tac_protoblock_', '').replace('.json', ''))
    else:
        # Legacy format - single version
        version_data = data
        block_id = os.path.basename(json_path).replace('.tac_protoblock_', '').replace('.json', '')
    
    # Extract data from the version
    task_description = version_data.get('task', {}).get('specification', '')
    
    test_data = version_data.get('test', {})
    test_specification = test_data.get('specification', '')
    test_data_generation = test_data.get('data', '')
    
    write_files = version_data.get('write_files', [])
    context_files = version_data.get('context_files', [])
    commit_message = version_data.get('commit_message', '')
    branch_name = version_data.get('branch_name', '')
    
    # Create and return the ProtoBlock
    return ProtoBlock(
        block_id=block_id,
        task_description=task_description,
        test_specification=test_specification,
        test_data_generation=test_data_generation,
        write_files=write_files,
        context_files=context_files,
        commit_message=commit_message,
        branch_name=branch_name
    ) 