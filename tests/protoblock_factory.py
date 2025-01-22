import json
import os
from dataclasses import dataclass, field
from typing import Dict, Optional
from uuid import uuid4
import logging

logger = logging.getLogger('tdac.core.protoblock_factory')

@dataclass
class ProtoBlockSpec:
    """Specification for creating a ProtoBlock"""
    block_id: str
    name: str
    description: str
    version: int = 1
    metadata: Dict[str, str] = field(default_factory=dict)
    dependencies: Dict[str, str] = field(default_factory=dict)

    def validate(self) -> bool:
        """Validate the ProtoBlock specification"""
        if not all([self.block_id, self.name, self.description]):
            return False
        if not isinstance(self.version, int) or self.version < 1:
            return False
        return True

class ProtoblockFactory:
    """Factory for creating and managing ProtoBlocks"""
    
    def __init__(self, output_dir: str = "protoblocks"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.version_history: Dict[str, int] = {}

    def create_protoblock(self, spec: ProtoBlockSpec) -> Optional[str]:
        """Create a new ProtoBlock from specification"""
        if not spec.validate():
            logger.error("Invalid ProtoBlock specification")
            return None
            
        # Check version history
        if spec.block_id in self.version_history:
            if spec.version <= self.version_history[spec.block_id]:
                logger.error(f"Version conflict for block {spec.block_id}")
                return None
        else:
            self.version_history[spec.block_id] = 0
            
        try:
            # Create output file
            filename = f"{spec.block_id}_v{spec.version}.json"
            filepath = os.path.join(self.output_dir, filename)
            
            # Write JSON data
            with open(filepath, 'w') as f:
                json.dump({
                    'block_id': spec.block_id,
                    'name': spec.name,
                    'description': spec.description,
                    'version': spec.version,
                    'metadata': spec.metadata,
                    'dependencies': spec.dependencies
                }, f, indent=2)
            
            # Update version history
            self.version_history[spec.block_id] = spec.version
            return filepath
            
        except (IOError, json.JSONDecodeError) as e:
            logger.error(f"Failed to create ProtoBlock: {str(e)}")
            return None

    def get_latest_version(self, block_id: str) -> int:
        """Get the latest version number for a block"""
        return self.version_history.get(block_id, 0)
