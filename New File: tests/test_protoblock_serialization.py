import json
import dataclasses
import unittest
from src.tac.protoblock.protoblock import ProtoBlock

class TestProtoBlockSerialization(unittest.TestCase):
    def test_branch_name_serialization(self):
        # Create a ProtoBlock with branch_name set
        proto = ProtoBlock(
            task_description="Test task",
            test_specification="Test spec",
            test_data_generation="Test data",
            write_files=["file1.py"],
            context_files=["context1.py"],
            block_id="testid",
            commit_message="TAC: Test commit",
            test_results=None,
            branch_name="feature/my-branch"
        )
        # Serialize to JSON
        proto_json = json.dumps(dataclasses.asdict(proto))
        # Deserialize it
        data = json.loads(proto_json)
        # Reconstruct ProtoBlock
        new_proto = ProtoBlock(**data)
        # Assert branch_name matches
        self.assertEqual(new_proto.branch_name, "feature/my-branch")

if __name__ == '__main__':
    unittest.main()
