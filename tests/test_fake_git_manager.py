import os
import tempfile
import shutil
import difflib

import pytest

# Import FakeGitManager from the appropriate module path
from src.tac.utils.git_manager import FakeGitManager

@pytest.fixture
def temp_repo():
    # Create a temporary directory for the fake repository
    repo_dir = tempfile.mkdtemp(prefix="test_repo_")
    try:
        # Create a sample file in the repository
        sample_file_path = os.path.join(repo_dir, "sample.txt")
        with open(sample_file_path, "w", encoding="utf-8") as f:
            f.write("Hello, world!")
        yield repo_dir
    finally:
        # Cleanup the temporary repository directory
        shutil.rmtree(repo_dir)

def test_commit_and_restore(temp_repo):
    # Initialize FakeGitManager with the temporary repository
    fake_git = FakeGitManager(temp_repo, cleanup_temp_dir=False)
    
    # The __init__ of FakeGitManager creates an initial commit "initial_commit"
    initial_commit = "initial_commit"
    
    sample_file_path = os.path.join(temp_repo, "sample.txt")
    
    # Read the initial content and assert it matches
    with open(sample_file_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert content == "Hello, world!"
    
    # Modify the file
    with open(sample_file_path, "w", encoding="utf-8") as f:
        f.write("Goodbye, world!")
    
    # Commit the changes with a new commit message
    assert fake_git.commit("modified_commit") is True
    
    # Verify that get_complete_diff shows the difference comparing with the initial commit
    diff_output = fake_git.get_complete_diff(initial_commit)
    # Check that the diff output contains information about modification of sample.txt
    assert "Modified File: sample.txt" in diff_output or "=== Modified File: sample.txt ===" in diff_output
    # Additionally check for a line that indicates removal or addition of text differences
    diff_lines = diff_output.splitlines()
    diff_found = any("Hello, world!" in line or "Goodbye, world!" in line for line in diff_lines)
    assert diff_found is True
    
    # Restore the initial commit
    assert fake_git.restore_commit(initial_commit) is True
    
    # After restoration, the file should contain the original content
    with open(sample_file_path, "r", encoding="utf-8") as f:
        restored_content = f.read()
    assert restored_content == "Hello, world!"
    
def test_branch_and_checkout_methods(temp_repo):
    # Initialize FakeGitManager with the temporary repository
    fake_git = FakeGitManager(temp_repo, cleanup_temp_dir=False)
    
    # Test get_current_branch returns 'main'
    current_branch = fake_git.get_current_branch()
    assert current_branch == "main"
    
    # Test create_or_switch_to_tac_branch returns True
    result_tac = fake_git.create_or_switch_to_tac_branch("tac_test")
    assert result_tac is True
    
    # Test checkout_branch returns True
    result_checkout = fake_git.checkout_branch("feature_branch", create=True)
    assert result_checkout is True
       
if __name__ == "__main__":
    pytest.main(["-v", "--maxfail=1"])