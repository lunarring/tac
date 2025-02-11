import os
import tempfile
import subprocess
import unittest

from src.tac.core.executor import ProtoBlockExecutor

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
        # Create a temporary directory and set it as current working directory.
        self.test_dir = tempfile.TemporaryDirectory()
        self.original_dir = os.getcwd()
        os.chdir(self.test_dir.name)
        # Initialize a new git repository.
        subprocess.run(["git", "init"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], check=True)
        # Create an initial commit so that branch switching works.
        with open("dummy.txt", "w", encoding="utf-8") as f:
            f.write("dummy")
        subprocess.run(["git", "add", "dummy.txt"], check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def tearDown(self):
        os.chdir(self.original_dir)
        self.test_dir.cleanup()

    def test_executor_switches_to_tac_branch(self):
        # Instantiate DummyProtoBlock and configuration with git enabled.
        block = DummyProtoBlock()
        config = {"git": {"enabled": True}}
        # Instantiate the executor with a dummy codebase.
        executor = ProtoBlockExecutor(block, config=config, codebase={})
        
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
        # Pre-create the TAC branch and check it out
        import io, logging
        subprocess.run(["git", "checkout", "-b", "tac_test123"], check=True)
        
        # Create dummy block with block_id = "test123"
        block = DummyProtoBlock()
        config = {"git": {"enabled": True}}
        executor = ProtoBlockExecutor(block, config=config, codebase={})
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
        
        from tac.core.git_manager import GitManager
        gm = GitManager()
        current_branch = gm.get_current_branch()
        self.assertEqual(current_branch, "tac_test123", msg=f"Expected branch 'tac_test123', got '{current_branch}'")
        self.assertIn("Already on a TAC branch: tac_test123. No branch switching necessary.", log_output)

if __name__ == '__main__':
    unittest.main()
