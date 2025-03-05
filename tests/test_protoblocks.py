import unittest
import json
from src.tac.blocks import ProtoBlock, ProtoBlockGenerator
import os
import tempfile
import time
import uuid

class TestProtoBlocks(unittest.TestCase):
    def test_save_and_validate_protoblock(self):
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
        factory = ProtoBlockGenerator()
        is_valid, error, _ = factory.verify_protoblock(protoblock_json)
        self.assertTrue(is_valid, f"Protoblock JSON should be valid, but got error: {error}")

        # Use temporary directory for file saving
        with tempfile.TemporaryDirectory() as temp_dir:
            # Change current working directory to the temporary directory for the test
            old_cwd = os.getcwd()
            os.chdir(temp_dir)
            
            try:
                # Generate a unique ID for testing
                unique_id = "test_" + str(int(time.time()))
                
                # Create a ProtoBlock instance
                protoblock = ProtoBlock(
                    task_description=valid_protoblock["task"]["specification"],
                    test_specification=valid_protoblock["test"]["specification"],
                    test_data_generation=valid_protoblock["test"]["data"],
                    write_files=valid_protoblock["write_files"],
                    context_files=valid_protoblock["context_files"],
                    block_id=unique_id,
                    commit_message=valid_protoblock["commit_message"],
                    branch_name=valid_protoblock["branch_name"]
                )
                
                # Save the protoblock using the new method
                file_path = protoblock.save()
                
                # Verify the file was created
                self.assertTrue(os.path.exists(file_path))
                self.assertIn(unique_id, file_path)
                
                # Test loading the protoblock
                loaded_protoblock = ProtoBlock.load(file_path)
                self.assertEqual(loaded_protoblock.block_id, unique_id)
                self.assertEqual(loaded_protoblock.task_description, valid_protoblock["task"]["specification"])
                
                # Clean up the test file
                os.remove(file_path)
            finally:
                # Restore the original working directory
                os.chdir(old_cwd)
