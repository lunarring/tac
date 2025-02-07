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

if __name__ == "__main__":
    unittest.main()
