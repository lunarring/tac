import unittest
from src.tac.agents.aider_agent import AiderAgent
from src.tac.protoblock.protoblock import ProtoBlock

class DummyProtoBlock(ProtoBlock):
    def __init__(self):
        self.task_description = "dummy task"
        self.test_specification = "dummy test"
        self.test_data_generation = "dummy data"
        self.write_files = ['path/to/file1.py', 'path/to/file2.py']
        self.context_files = ['path/to/context1.py']
        self.block_id = "dummyid"
        self.commit_message = "dummy commit"
        self.test_results = None

class TestAiderAgentCommand(unittest.TestCase):
    def test_build_command_includes_files(self):
        # Create dummy protoblock
        dummy_proto = DummyProtoBlock()
        # Create agent with a dummy model entry in the configuration
        config = {'aider': {'model': 'dummy-model'}}
        agent = AiderAgent(config)
        command_str = agent.build_command(dummy_proto)
        # Verify that command string contains the expected --file and --read arguments
        self.assertIn("--file=path/to/file1.py", command_str)
        self.assertIn("--file=path/to/file2.py", command_str)
        self.assertIn("--read=path/to/context1.py", command_str)

if __name__ == '__main__':
    unittest.main()
