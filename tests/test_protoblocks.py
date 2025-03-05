import os
import json
from src.tac.protoblock import protoblock_io
from src.tac.protoblock.factory import ProtoBlockFactory
import time

def test_save_and_validate_protoblock(tmp_path):
    # Create a valid protoblock dictionary (legacy format)
    valid_protoblock = {
        "task": {"specification": "Test task specification"},
        "test": {
            "specification": "Test test specification",
            "data": "Test test data",
            "replacements": []
        },
        "write_files": ["dummy.py"],
        "context_files": ["main.py"],
        "commit_message": "TAC: Test commit message",
        "branch_name": "tac/test-branch"
    }
    # Convert dictionary to JSON string
    protoblock_json = json.dumps(valid_protoblock)

    # Validate using the factory's verification method
    factory = ProtoBlockFactory()
    is_valid, error, _ = factory.verify_protoblock(protoblock_json)
    assert is_valid, f"Protoblock JSON should be valid, but got error: {error}"

    # Use temporary directory for file saving
    temp_dir = tmp_path / "protoblock_test_dir"
    temp_dir.mkdir()
    # Change current working directory to the temporary directory for the test
    old_cwd = os.getcwd()
    os.chdir(temp_dir)
    
    try:
        # Generate a unique ID for testing
        unique_id = "test_" + str(int(time.time()))
        
        # Save the protoblock using protoblock_io.save_protoblock
        file_path, block_id = protoblock_io.save_protoblock(protoblock_json, template_type="test", unique_id=unique_id)
        
        # Verify the file was created
        assert os.path.exists(file_path)
        assert block_id == unique_id
        
        # Clean up the test file
        os.remove(file_path)
    finally:
        # Restore the original working directory
        os.chdir(old_cwd)
