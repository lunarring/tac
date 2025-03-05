import pytest
import json
from src.tac.protoblock.factory import ProtoBlockFactory

def test_missing_test_key():
    # Create a protoblock missing the 'test' key
    protoblock = {
        'task': {'specification': 'dummy task'},
        'write_files': [],
        'context_files': [],
        'commit_message': 'TAC: Dummy commit'
    }
    factory = ProtoBlockFactory()
    valid, error, _ = factory.verify_protoblock(json.dumps(protoblock))
    assert valid == False
    assert "Missing required key: test" in error

def test_missing_commit_message_key():
    # Create a protoblock missing the 'commit_message' key
    protoblock = {
        'task': {'specification': 'dummy task'},
        'test': {'specification': 'dummy test', 'data': {}, 'replacements': {}},
        'write_files': [],
        'context_files': []
    }
    factory = ProtoBlockFactory()
    valid, error, _ = factory.verify_protoblock(json.dumps(protoblock))
    assert valid == False
    assert "Missing required key: commit_message" in error

if __name__ == '__main__':
    pytest.main([__file__])
