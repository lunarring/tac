import unittest
import os
import json
import tempfile
import sys
from pathlib import Path
from unittest.mock import patch, mock_open
from uuid import uuid4

# Adjust import path to find the module
current_dir = Path(__file__).parent
core_dir = current_dir.parent / "tdac" / "core"
sys.path.insert(0, str(core_dir))

from protoblock_factory import ProtoblockFactory, ProtoBlockSpec

class TestProtoblockFactory(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.factory = ProtoblockFactory(output_dir=self.temp_dir.name)
        
    def tearDown(self):
        self.temp_dir.cleanup()

    def test_create_valid_protoblock(self):
        """Test creating a valid protoblock"""
        spec = ProtoBlockSpec(
            block_id=str(uuid4()),
            name="Test Block",
            description="Test Description",
            version=1,
            metadata={"key": "value"},
            dependencies={"dep1": "1.0.0"}
        )
        
        result = self.factory.create_protoblock(spec)
        self.assertIsNotNone(result)
        
        # Verify file contents
        with open(result, 'r') as f:
            data = json.load(f)
            self.assertEqual(data['name'], spec.name)
            self.assertEqual(data['description'], spec.description)
            self.assertEqual(data['version'], spec.version)
            self.assertEqual(data['metadata'], spec.metadata)
            self.assertEqual(data['dependencies'], spec.dependencies)

    def test_create_invalid_protoblock(self):
        """Test creating a protoblock with invalid specification"""
        # Missing required fields
        spec = ProtoBlockSpec(
            block_id="",
            name="",
            description="",
            version=1
        )
        
        result = self.factory.create_protoblock(spec)
        self.assertIsNone(result)

    def test_version_tracking(self):
        """Test version history tracking"""
        block_id = str(uuid4())
        
        # Create first version
        spec1 = ProtoBlockSpec(
            block_id=block_id,
            name="Test Block",
            description="Test Description",
            version=1
        )
        self.factory.create_protoblock(spec1)
        self.assertEqual(self.factory.get_latest_version(block_id), 1)
        
        # Create second version
        spec2 = ProtoBlockSpec(
            block_id=block_id,
            name="Test Block",
            description="Test Description",
            version=2
        )
        self.factory.create_protoblock(spec2)
        self.assertEqual(self.factory.get_latest_version(block_id), 2)

    def test_version_conflict(self):
        """Test version conflict detection"""
        block_id = str(uuid4())
        
        spec1 = ProtoBlockSpec(
            block_id=block_id,
            name="Test Block",
            description="Test Description",
            version=2
        )
        self.factory.create_protoblock(spec1)
        
        # Attempt to create with same version
        spec2 = ProtoBlockSpec(
            block_id=block_id,
            name="Test Block",
            description="Test Description",
            version=2
        )
        result = self.factory.create_protoblock(spec2)
        self.assertIsNone(result)

    @patch('builtins.open', side_effect=IOError("Mocked IO Error"))
    def test_file_creation_failure(self, mock_file):
        """Test handling of file creation failures"""
        spec = ProtoBlockSpec(
            block_id=str(uuid4()),
            name="Test Block",
            description="Test Description",
            version=1
        )
        
        result = self.factory.create_protoblock(spec)
        self.assertIsNone(result)

    def test_directory_creation(self):
        """Test that output directory is created if it doesn't exist"""
        new_dir = os.path.join(self.temp_dir.name, "new_dir")
        factory = ProtoblockFactory(output_dir=new_dir)
        
        spec = ProtoBlockSpec(
            block_id=str(uuid4()),
            name="Test Block",
            description="Test Description",
            version=1
        )
        
        result = factory.create_protoblock(spec)
        self.assertIsNotNone(result)
        self.assertTrue(os.path.exists(new_dir))

    def test_invalid_version_number(self):
        """Test handling of invalid version numbers"""
        spec = ProtoBlockSpec(
            block_id=str(uuid4()),
            name="Test Block",
            description="Test Description",
            version=0  # Invalid version
        )
        
        result = self.factory.create_protoblock(spec)
        self.assertIsNone(result)

if __name__ == '__main__':
    unittest.main()
