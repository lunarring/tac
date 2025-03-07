import unittest
from src.tac.blocks import ProtoBlockGenerator
import json

class TestProtoBlockJSON(unittest.TestCase):
    
    def test_valid_json(self):
        # Valid JSON string with all required fields
        json_data = """
        {
            "task": {"specification": "Test task"},
            "test": {"specification": "Test spec", "data": "Test data"},
            "write_files": ["file1.py", "file2.py"],
            "context_files": ["context1.py", "context2.py"],
            "commit_message": "Test commit",
            "branch_name": "test-branch",
            "trusty_agents": ["pytest", "plausibility"]
        }
        """
        
        factory = ProtoBlockGenerator()
        valid, error, _ = factory.verify_protoblock(json_data)
        assert valid == True
        assert error == ""

    def test_missing_test_key(self):
        # Create a protoblock missing the 'test' key
        protoblock = {
            'task': {'specification': 'dummy task'},
            'write_files': [],
            'context_files': [],
            'commit_message': 'TAC: Dummy commit'
        }
        factory = ProtoBlockGenerator()
        valid, error, _ = factory.verify_protoblock(json.dumps(protoblock))
        assert valid == False
        assert "Missing required key: test" in error

    def test_missing_commit_message_key(self):
        # Create a protoblock missing the 'commit_message' key
        protoblock = {
            'task': {'specification': 'dummy task'},
            'test': {'specification': 'dummy test', 'data': {}, 'replacements': {}},
            'write_files': [],
            'context_files': []
        }
        factory = ProtoBlockGenerator()
        valid, error, _ = factory.verify_protoblock(json.dumps(protoblock))
        assert valid == False
        assert "Missing required key: commit_message" in error

if __name__ == '__main__':
    unittest.main()
