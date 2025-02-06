import os
import json
from src.tac.protoblock import manager

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
        "commit_message": "TAC: Test commit message"
    }
    # Convert dictionary to JSON string
    protoblock_json = json.dumps(valid_protoblock)

    # Validate using the manager's validation function
    is_valid, error = manager.validate_protoblock_json(protoblock_json)
    assert is_valid, f"Protoblock JSON should be valid, but got error: {error}"

    # Use temporary directory for file saving
    temp_dir = tmp_path / "protoblock_test_dir"
    temp_dir.mkdir()
    # Change current working directory to the temporary directory for the test
    old_cwd = os.getcwd()
    os.chdir(temp_dir)
    try:
        unique_id = "test123"
        # Save the protoblock using manager.save_protoblock
        file_path, block_id = manager.save_protoblock(protoblock_json, template_type="test", unique_id=unique_id)

        # Verify that the file name matches the expected pattern and the block_id is as provided.
        expected_file_name = f".tac_protoblock_{unique_id}.json"
        assert file_path == expected_file_name, f"Expected file name {expected_file_name} but got {file_path}"
        assert block_id == unique_id, "Block id should match the provided unique id"
        assert os.path.exists(file_path), f"File {file_path} should exist"

        # Load the file content and check for required keys
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            for key in ["task", "test", "write_files", "context_files", "commit_message"]:
                assert key in data, f"Key {key} missing in saved protoblock file."
    finally:
        # Restore the original working directory
        os.chdir(old_cwd)
