import os
import subprocess
import tempfile
import unittest

from src.tac.core.git_manager import GitManager

class TestGitManager(unittest.TestCase):
    def setUp(self):
        # Create temporary directory and initialize a git repository
        self.test_dir = tempfile.TemporaryDirectory()
        self.repo_path = self.test_dir.name
        subprocess.run(["git", "init"], cwd=self.repo_path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # Set Git user config for commits
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.repo_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=self.repo_path, check=True)
        
        # Create a file and commit it
        with open(os.path.join(self.repo_path, "test.txt"), "w", encoding="utf-8") as f:
            f.write("Hello world")
        subprocess.run(["git", "add", "test.txt"], cwd=self.repo_path, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=self.repo_path, check=True)

    def tearDown(self):
        self.test_dir.cleanup()

    def test_revert_changes(self):
        # Modify the committed file (tracked, unstaged change)
        with open(os.path.join(self.repo_path, "test.txt"), "a", encoding="utf-8") as f:
            f.write("\nNew line")
        # Create an untracked file
        with open(os.path.join(self.repo_path, "untracked.txt"), "w", encoding="utf-8") as f:
            f.write("untracked file content")
        
        # Ensure changes exist before reverting
        status_before = subprocess.run(
            ["git", "status", "--porcelain"], cwd=self.repo_path, check=True, stdout=subprocess.PIPE
        ).stdout.decode().strip()
        self.assertNotEqual(status_before, "", msg="Repository should have changes before revert.")

        # Instantiate GitManager and revert changes
        gm = GitManager(repo_path=self.repo_path)
        result = gm.revert_changes()
        self.assertTrue(result, msg="revert_changes() failed.")

        # Verify that the working directory is clean
        status_after = subprocess.run(
            ["git", "status", "--porcelain"], cwd=self.repo_path, check=True, stdout=subprocess.PIPE
        ).stdout.decode().strip()
        self.assertEqual(status_after, "", msg="Repository working directory is not clean after revert_changes.")

    def test_get_current_branch(self):
        # Instantiate GitManager
        gm = GitManager(repo_path=self.repo_path)
        # Monkey-patch subprocess.check_output to simulate a custom branch name.
        original_check_output = subprocess.check_output
        subprocess.check_output = lambda cmd, cwd, encoding: "feature/update-branch\n"
        branch = gm.get_current_branch()
        self.assertEqual(branch, "feature/update-branch")
        # Restore the original check_output method.
        subprocess.check_output = original_check_output

    def test_create_or_switch_to_tac_branch(self):
        # Start from a non-primary branch, e.g., 'develop'
        subprocess.run(["git", "checkout", "-b", "develop"], cwd=self.repo_path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        gm = GitManager(repo_path=self.repo_path)
        tac_id = "tac_feature123"
        # Create new tac branch
        result = gm.create_or_switch_to_tac_branch(tac_id)
        self.assertTrue(result, msg="Failed to create or switch to TAC branch")
        # Check active branch is the new tac branch
        active_branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=self.repo_path, encoding="utf-8").strip()
        self.assertEqual(active_branch, tac_id, msg="Active branch is not the TAC branch after creation")

    def test_switch_existing_tac_branch(self):
        # Create a tac branch first
        tac_id = "tac_existing"
        subprocess.run(["git", "checkout", "-b", tac_id], cwd=self.repo_path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # Switch to a different branch (create 'develop' if necessary)
        subprocess.run(["git", "checkout", "-b", "develop"], cwd=self.repo_path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        gm = GitManager(repo_path=self.repo_path)
        # Switch back to the existing tac branch
        result = gm.create_or_switch_to_tac_branch(tac_id)
        self.assertTrue(result, msg="Failed to switch back to existing TAC branch")
        active_branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=self.repo_path, encoding="utf-8").strip()
        self.assertEqual(active_branch, tac_id, msg="Active branch is not the expected existing TAC branch")
        
if __name__ == "__main__":
    unittest.main()
