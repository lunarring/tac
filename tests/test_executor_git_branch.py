import os
import tempfile
import subprocess
import unittest
import io
import logging

from src.tac.core.executor import ProtoBlockExecutor
from src.tac.core.config import GitConfig

# Define a dummy ProtoBlock with minimal attributes.
class DummyProtoBlock:
    def __init__(self):
        self.block_id = "test123"
        self.task_description = "dummy task"
        self.test_specification = "dummy spec"
        self.test_data_generation = "dummy data"
        self.write_files = {}
        self.context_files = {}
        self.commit_message = "dummy commit"

    def create_agent(self, config):
        return DummyAgent()

# Define a dummy Agent that does nothing in run().
class DummyAgent:
    def run(self, protoblock, previous_analysis=None):
        pass

class TestExecutorGitBranch(unittest.TestCase):
    def setUp(self):
        # Override GitManager methods to avoid expensive git subprocess calls.
        from src.tac.core.git_manager import GitManager
        GitManager.dummy_branch = ""
        def dummy_get_current(self):
            return GitManager.dummy_branch
        def dummy_create_or_switch(self, tac_id):
            GitManager.dummy_branch = tac_id
            return True
        GitManager.get_current_branch = dummy_get_current
        GitManager.create_or_switch_to_tac_branch = dummy_create_or_switch

    def tearDown(self):
        pass

    def test_executor_switches_to_tac_branch(self):
        # Instantiate DummyProtoBlock and configuration with git enabled.
        block = DummyProtoBlock()
        config_override = {
            'git': {'enabled': True}
        }
        # Instantiate the executor with a dummy codebase.
        executor = ProtoBlockExecutor(block, config_override=config_override, codebase={})
        
        # Stub out run_tests to avoid running any real tests.
        executor.run_tests = lambda test_path=None: True
        
        # Execute the block. This will invoke the branch-switch logic.
        executor.execute_block()
        
        # Check that the current branch is "tac_test123"
        # Create a new GitManager pointing to the current repository.
        from tac.core.git_manager import GitManager
        gm = GitManager()
        current_branch = gm.get_current_branch()
        self.assertEqual(current_branch, "tac_test123", msg=f"Expected branch 'tac_test123', got '{current_branch}'")

    def test_executor_no_switch_when_already_on_tac_branch(self):
        # Simulate already being on TAC branch
        from src.tac.core.git_manager import GitManager
        GitManager.dummy_branch = "tac_test123"
        
        # Create dummy block with block_id = "test123"
        block = DummyProtoBlock()
        config_override = {
            'git': {'enabled': True}
        }
        executor = ProtoBlockExecutor(block, config_override=config_override, codebase={})
        executor.run_tests = lambda test_path=None: True
        
        # Capture logs from the executor
        log_capture = io.StringIO()
        log_handler = logging.StreamHandler(log_capture)
        logger = logging.getLogger("tac.core.executor")
        logger.setLevel(logging.INFO)
        logger.addHandler(log_handler)
        
        executor.execute_block()
        
        logger.removeHandler(log_handler)
        log_output = log_capture.getvalue()
        
        # Check that the executor did not switch branches and remains on tac_test123.
        from src.tac.core.git_manager import GitManager
        gm = GitManager()
        current_branch = gm.get_current_branch()
        self.assertEqual(current_branch, "tac_test123", msg=f"Expected branch 'tac_test123', got '{current_branch}'")
        self.assertIn("Already on a TAC branch: tac_test123. No branch switching necessary.", log_output)

if __name__ == '__main__':
    unittest.main()
