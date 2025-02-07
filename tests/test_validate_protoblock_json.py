import pytest
from src.tac.protoblock.manager import validate_protoblock_json

def test_missing_test_key():
    # Create a protoblock missing the 'test' key
    protoblock = {
        'task': {'specification': 'dummy task'},
        'write_files': [],
        'context_files': [],
        'commit_message': 'TAC: Dummy commit'
    }
    valid, error = validate_protoblock_json(protoblock)
    assert valid == False
    assert "Missing required top-level key: test" in error

def test_missing_commit_message_key():
    # Create a protoblock missing the 'commit_message' key
    protoblock = {
        'task': {'specification': 'dummy task'},
        'test': {'specification': 'dummy test', 'data': {}, 'replacements': {}},
        'write_files': [],
        'context_files': []
    }
    valid, error = validate_protoblock_json(protoblock)
    assert valid == False
    assert "Missing required top-level key: commit_message" in error

if __name__ == '__main__':
    pytest.main([__file__])
