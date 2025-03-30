from dataclasses import dataclass
from typing import Dict, Any, Optional, Union, ClassVar, List
import json
import os
from datetime import datetime
import logging

from tac.core.config import config

logger = logging.getLogger(__name__)

@dataclass
class ProtoBlock:
    """
    A structured specification for a coding task that serves as the contract between planning and execution.
    
    Contains all information needed to implement a change:
    - Task description and requirements
    - Files to modify and reference during implementation
    - Version control metadata
    - Trusted agents to delegate trust assurances to
    
    ProtoBlocks can be serialized to JSON for storage and loaded back for execution.
    """
    task_description: str
    write_files: list
    context_files: list
    block_id: str
    trusty_agents: List[str] = None
    trusty_agent_prompts: Dict[str, str] = None
    branch_name: str = None
    commit_message: str = None
    image_url: Optional[str] = None
    visual_description: Optional[str] = None

    def __post_init__(self):
        # Set default value for trusty_agents from config if None
        if self.trusty_agents is None:
            self.trusty_agents = config.general.trusty_agents.default_trusty_agents
        
        # Set default empty dict for trusty_agent_prompts if None
        if self.trusty_agent_prompts is None:
            self.trusty_agent_prompts = {}

    @classmethod
    def load(cls, json_path: str) -> 'ProtoBlock':
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
        write_files = version_data.get('write_files', [])
        context_files = version_data.get('context_files', [])
        commit_message = version_data.get('commit_message', '')
        branch_name = version_data.get('branch_name', '')
        trusty_agents = version_data.get('trusty_agents', config.general.trusty_agents.default_trusty_agents)
        trusty_agent_prompts = version_data.get('trusty_agent_prompts', {})
        image_url = version_data.get('image_url', None)
        visual_description = version_data.get('visual_description', None)
        
        # Create and return the ProtoBlock
        return cls(
            block_id=block_id,
            task_description=task_description,
            write_files=write_files,
            context_files=context_files,
            commit_message=commit_message,
            branch_name=branch_name,
            trusty_agents=trusty_agents,
            trusty_agent_prompts=trusty_agent_prompts,
            image_url=image_url,
            visual_description=visual_description
        )

    def save(self, filename: Optional[str] = None) -> str:
        """
        Save the protoblock to a file.
        
        Args:
            filename: Optional filename to save to. If not provided, will use default format .tac_protoblock_{block_id}.json
            
        Returns:
            Path to the saved protoblock file
        """
        # Ensure all paths are relative
        write_files = [os.path.relpath(path) if os.path.isabs(path) else path for path in self.write_files]
        context_files = [os.path.relpath(path) if os.path.isabs(path) else path for path in self.context_files]
        
        version_data = {
            "task": {
                "specification": self.task_description
            },
            "write_files": write_files,
            "context_files": context_files,
            "commit_message": self.commit_message,
            "branch_name": self.branch_name,
            "trusty_agents": self.trusty_agents,
            "trusty_agent_prompts": self.trusty_agent_prompts,
            "timestamp": datetime.now().isoformat(),
            "image_url": self.image_url,
            "visual_description": self.visual_description
        }
        
        # Use provided filename or generate default one
        if filename is None:
            filename = f".tac_protoblock_{self.block_id}.json"
        
        # Load existing data if file exists, otherwise create new structure
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                file_data = json.load(f)
                if not isinstance(file_data, dict) or 'versions' not in file_data:
                    # Convert old format to new format
                    file_data = {
                        'block_id': self.block_id,
                        'versions': [file_data]  # Old data becomes first version
                    }
        else:
            file_data = {
                'block_id': self.block_id,
                'versions': []
            }
        
        # Add new version
        file_data['versions'].append(version_data)
            
        with open(filename, 'w') as f:
            json.dump(file_data, f, indent=2)
            
        return filename

    def to_dict(self) -> dict:
        """
        Convert the ProtoBlock to a dictionary.
        
        Returns:
            dict: Dictionary representation of the ProtoBlock
        """
        return {
            "task": {
                "specification": self.task_description
            },
            "write_files": self.write_files,
            "context_files": self.context_files,
            "commit_message": self.commit_message,
            "branch_name": self.branch_name,
            "block_id": self.block_id,
            "trusty_agents": self.trusty_agents,
            "trusty_agent_prompts": self.trusty_agent_prompts,
            "image_url": self.image_url,
            "visual_description": self.visual_description
        }