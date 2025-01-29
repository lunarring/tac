import unittest
from unittest.mock import patch, MagicMock
import json

from src.tac.protoblock.factory import ProtoBlockFactory
from src.tac.protoblock.protoblock import ProtoBlock

class TestProtoBlockFactory(unittest.TestCase):
    @patch('src.tac.protoblock.factory.LLMClient')
    def test_create_protoblock(self, mock_llm_client):
        # Define sample configuration dictionary
        sample_config = {
            "task_description": "Implement a new feature for user authentication.",
            "test_specification": "Ensure that user login and logout functionalities work correctly.",
            "test_data_generation": "Sample user credentials and session tokens.",
            "write_files": [
                "src/tac/protoblock/authentication.py",
                "src/tac/protoblock/utils.py"
            ],
            "context_files": [
                "src/tac/protoblock/protoblock.py",
                "src/tac/protoblock/factory.py"
            ],
            "commit_message": "Add user authentication feature."
        }

        # Define expected ProtoBlock attributes based on sample_config
        expected_proto_block_attributes = {
            "task_description": sample_config["task_description"],
            "test_specification": sample_config["test_specification"],
            "test_data_generation": sample_config["test_data_generation"],
            "write_files": sample_config["write_files"],
            "context_files": sample_config["context_files"],
            "commit_message": f"tac: {sample_config['commit_message']}"
        }

        # Mock LLMClient's chat_completion method to return a predetermined JSON response
        mock_llm_instance = MagicMock()
        mock_llm_instance.chat_completion.return_value = json.dumps({
            "task": {
                "specification": sample_config["task_description"]
            },
            "test": {
                "specification": sample_config["test_specification"],
                "data": sample_config["test_data_generation"]
            },
            "write_files": sample_config["write_files"],
            "context_files": sample_config["context_files"],
            "commit_message": sample_config["commit_message"]
        })
        mock_llm_client.return_value = mock_llm_instance

        # Initialize ProtoBlockFactory
        factory = ProtoBlockFactory()

        # Define sample seed instructions (could be more detailed based on actual implementation)
        seed_instructions = "Create a Protoblock for user authentication feature."

        # Invoke create_protoblock to create a ProtoBlock instance
        proto_block = factory.create_protoblock(seed_instructions)

        # Assertions to verify that the ProtoBlock instance has correct attributes
        self.assertIsInstance(proto_block, ProtoBlock, "The created object is not an instance of ProtoBlock.")
        self.assertEqual(proto_block.task_description, expected_proto_block_attributes["task_description"],
                         "Task description does not match.")
        self.assertEqual(proto_block.test_specification, expected_proto_block_attributes["test_specification"],
                         "Test specification does not match.")
        self.assertEqual(proto_block.test_data_generation, expected_proto_block_attributes["test_data_generation"],
                         "Test data generation does not match.")
        self.assertEqual(proto_block.write_files, expected_proto_block_attributes["write_files"],
                         "Write files do not match.")
        self.assertEqual(proto_block.context_files, expected_proto_block_attributes["context_files"],
                         "Context files do not match.")
        self.assertEqual(proto_block.commit_message, expected_proto_block_attributes["commit_message"],
                         "Commit message does not match.")

        # Additional behavior tests can be added here
        # For example, testing methods of ProtoBlock if any

if __name__ == '__main__':
    unittest.main()
