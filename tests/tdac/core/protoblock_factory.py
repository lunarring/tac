import os
import json
from pathlib import Path
from uuid import uuid4
from dataclasses import dataclass
from typing import Dict, Optional

@dataclass
class ProtoBlockSpec:
    block_id: str
    name: str
    description: str
    version: int
    metadata: Optional[Dict] = None
    dependencies: Optional[Dict] = None

class ProtoblockFactory:
    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        self.version_history = {}
        os.makedirs(self.output_dir, exist_ok=True)

    def create_protoblock(self, spec: ProtoBlockSpec) -> Optional[str]:
        """Create a protoblock from specification"""
        if not self._validate_spec(spec):
            return None
        
        # Check version conflicts
        if spec.block_id in self.version_history:
            if spec.version <= self.version_history[spec.block_id]:
                return None
        
        # Create block data
        block_data = {
            'block_id': spec.block_id,
            'name': spec.name,
            'description': spec.description,
            'version': spec.version,
            'metadata': spec.metadata or {},
            'dependencies': spec.dependencies or {}
        }
        
        # Create output file
        filename = f"{spec.block_id}_v{spec.version}.json"
        output_path = os.path.join(self.output_dir, filename)
        
        try:
            with open(output_path, 'w') as f:
                json.dump(block_data, f, indent=2)
            
            # Update version history
            self.version_history[spec.block_id] = spec.version
            return output_path
        except (IOError, json.JSONDecodeError):
            return None

    def get_latest_version(self, block_id: str) -> int:
        """Get latest version for a block ID"""
        return self.version_history.get(block_id, 0)

    def _validate_spec(self, spec: ProtoBlockSpec) -> bool:
        """Validate the protoblock specification"""
        if not spec.block_id or not isinstance(spec.block_id, str):
            return False
        if not spec.name or not isinstance(spec.name, str):
            return False
        if not spec.description or not isinstance(spec.description, str):
            return False
        if not isinstance(spec.version, int) or spec.version < 1:
            return False
        return True
