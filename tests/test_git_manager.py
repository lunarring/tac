import unittest
from unittest.mock import patch, MagicMock
from tdac.core.git_manager import GitManager
import git

class TestGitManager(unittest.TestCase):
    @patch('tdac.core.git_manager.git.Repo')
    def test_initialization_success(self, mock_repo):
        """Test successful initialization of GitManager with a valid git repository."""
        # Mock successful repo initialization
        mock_repo.return_value = MagicMock()
        
        manager = GitManager()
        
        mock_repo.assert_called_with('.')
        self.assertIsNotNone(manager.repo)
        self.assertTrue(hasattr(manager.repo, 'git'))
        self.assertTrue(callable(getattr(manager.repo, 'git', None)))
    
    @patch('tdac.core.git_manager.git.Repo')
    def test_initialization_with_custom_path(self, mock_repo):
        """Test initialization of GitManager with a custom repository path."""
        # Mock successful repo initialization
        mock_repo.return_value = MagicMock()
        
        repo_path = '/path/to/repo'
        manager = GitManager(repo_path=repo_path)
        
        mock_repo.assert_called_with(repo_path)
        self.assertIsNotNone(manager.repo)
    
    @patch('tdac.core.git_manager.git.Repo')
    def test_initialization_invalid_repo(self, mock_repo):
        """Test initialization of GitManager with an invalid git repository."""
        # Mock InvalidGitRepositoryError
        mock_repo.side_effect = git.exc.InvalidGitRepositoryError
        
        with self.assertLogs('tdac.core.git_manager', level='ERROR') as log:
            manager = GitManager()
            self.assertIsNone(manager.repo)
            self.assertIn("Not a git repository. Please initialize git first.", log.output[0])
    
    @patch('tdac.core.git_manager.git.Repo')
    def test_initialization_git_command_error(self, mock_repo):
        """Test initialization of GitManager when a GitCommandError occurs."""
        # Mock GitCommandError during repo initialization
        mock_repo.side_effect = git.exc.GitCommandError(['init'], 1)
        
        with self.assertLogs('tdac.core.git_manager', level='ERROR') as log:
            manager = GitManager()
            self.assertIsNone(manager.repo)
            self.assertIn("Error initializing git repository", log.output[0])
    
    @patch('tdac.core.git_manager.git.Repo')
    def test_check_status_clean(self, mock_repo):
        """Test check_status method when the repository is clean."""
        # Mock a clean repository
        mock_repo_instance = MagicMock()
        mock_repo_instance.is_dirty.return_value = False
        mock_repo.return_value = mock_repo_instance
        
        manager = GitManager()
        status = manager.check_status()
        
        mock_repo_instance.is_dirty.assert_called_with(untracked_files=True)
        self.assertTrue(status)
    
    @patch('tdac.core.git_manager.git.Repo')
    def test_check_status_dirty(self, mock_repo):
        """Test check_status method when the repository has uncommitted changes."""
        # Mock a dirty repository
        mock_repo_instance = MagicMock()
        mock_repo_instance.is_dirty.return_value = True
        mock_repo_instance.git.status.return_value = "On branch master\nChanges not staged for commit:"
        mock_repo.return_value = mock_repo_instance
    
        with self.assertLogs('tdac.core.git_manager', level='ERROR') as log:
            manager = GitManager()
            status = manager.check_status()
    
            mock_repo_instance.is_dirty.assert_called_with(untracked_files=True)
            mock_repo_instance.git.status.assert_called()
            self.assertFalse(status)
            self.assertIn("Git working tree is not clean. Please commit or stash your changes before running TDAC!", log.output[0])
    
    @patch('tdac.core.git_manager.git.Repo')
    def test_check_status_git_command_error(self, mock_repo):
        """Test check_status method when a GitCommandError occurs during status check."""
        # Mock GitCommandError during status check
        mock_repo_instance = MagicMock()
        mock_repo_instance.is_dirty.side_effect = git.exc.GitCommandError(['status'], 1)
        mock_repo.return_value = mock_repo_instance
    
        with self.assertLogs('tdac.core.git_manager', level='ERROR') as log:
            manager = GitManager()
            status = manager.check_status()
    
            mock_repo_instance.is_dirty.assert_called_with(untracked_files=True)
            self.assertFalse(status)
            self.assertIn("Error checking git status", log.output[0])
    
    @patch('tdac.core.git_manager.git.Repo')
    def test_handle_post_execution_no_repo(self, mock_repo):
        """Test handle_post_execution method when there is no git repository."""
        # Mock repo as None
        mock_repo.return_value = None
        
        manager = GitManager()
        result = manager.handle_post_execution(config={'git': {'auto_push': True}}, commit_message="Test commit")
        
        self.assertTrue(result)
    
    @patch('tdac.core.git_manager.git.Repo')
    def test_handle_post_execution_auto_push_false(self, mock_repo):
        """Test handle_post_execution method when auto_push is set to False."""
        # Mock repository with auto_push=False
        mock_repo_instance = MagicMock()
        mock_repo.return_value = mock_repo_instance
        
        manager = GitManager()
        result = manager.handle_post_execution(config={'git': {'auto_push': False}}, commit_message="Test commit")
        
        self.assertTrue(result)
        mock_repo_instance.git.add.assert_not_called()
        mock_repo_instance.git.commit.assert_not_called()
        mock_repo_instance.git.push.assert_not_called()
    
    @patch('tdac.core.git_manager.git.Repo')
    def test_handle_post_execution_with_commit_message(self, mock_repo):
        """Test handle_post_execution method with a provided commit message."""
        # Mock successful git operations with provided commit message
        mock_repo_instance = MagicMock()
        mock_repo.return_value = mock_repo_instance
        
        manager = GitManager()
        result = manager.handle_post_execution(config={'git': {'auto_push': True}}, commit_message="Manual commit message")
        
        mock_repo_instance.git.add.assert_called_with('.')
        mock_repo_instance.git.commit.assert_called_with('-m', "Manual commit message")
        mock_repo_instance.git.push.assert_called()
        self.assertTrue(result)
    
    @patch('tdac.core.git_manager.git.Repo')
    def test_handle_post_execution_auto_push_true_no_commit_message(self, mock_repo):
        """Test handle_post_execution method with auto_push=True and no commit message provided."""
        # Mock successful git operations with auto-generated commit message
        mock_repo_instance = MagicMock()
        mock_repo_instance.git.diff.return_value = "file1.py\nfile2.py\nfile3.py\nfile4.py"
        mock_repo.return_value = mock_repo_instance
        
        manager = GitManager()
        result = manager.handle_post_execution(config={'git': {'auto_push': True}})
        
        mock_repo_instance.git.add.assert_called_with('.')
        expected_message = "TDAC: Successfully implemented changes in file1.py, file2.py, file3.py and 1 more files"
        mock_repo_instance.git.commit.assert_called_with('-m', expected_message)
        mock_repo_instance.git.push.assert_called()
        self.assertTrue(result)
    
    @patch('tdac.core.git_manager.git.Repo')
    def test_handle_post_execution_git_command_error(self, mock_repo):
        """Test handle_post_execution method when a GitCommandError occurs during git operations."""
        # Mock GitCommandError during git operations
        mock_repo_instance = MagicMock()
        mock_repo_instance.git.add.side_effect = git.exc.GitCommandError(['add'], 1)
        mock_repo.return_value = mock_repo_instance
        
        with self.assertLogs('tdac.core.git_manager', level='ERROR') as log:
            manager = GitManager()
            result = manager.handle_post_execution(config={'git': {'auto_push': True}}, commit_message="Test commit")
            
            mock_repo_instance.git.add.assert_called_with('.')
            mock_repo_instance.git.commit.assert_not_called()
            mock_repo_instance.git.push.assert_not_called()
            self.assertFalse(result)
            self.assertIn("Error during git operations", log.output[0])
    
    @patch('tdac.core.git_manager.git.Repo')
    def test_revert_changes_success(self, mock_repo):
        """Test successfully reverting changes in the repository."""
        # Mock successful revert of changes
        mock_repo_instance = MagicMock()
        mock_repo.return_value = mock_repo_instance
        
        manager = GitManager()
        result = manager.revert_changes()
        
        mock_repo_instance.git.reset.assert_called_with('--hard')
        mock_repo_instance.git.clean.assert_called_with('-fd')
        self.assertTrue(result)
    
    @patch('tdac.core.git_manager.git.Repo')
    def test_revert_changes_no_repo(self, mock_repo):
        """Test revert_changes method when there is no git repository."""
        # Mock repo as None
        mock_repo.return_value = None
        
        manager = GitManager()
        result = manager.revert_changes()
        
        self.assertFalse(result)
    
    @patch('tdac.core.git_manager.git.Repo')
    def test_revert_changes_git_command_error(self, mock_repo):
        """Test revert_changes method when a GitCommandError occurs during reverting."""
        # Mock GitCommandError during revert
        mock_repo_instance = MagicMock()
        mock_repo_instance.git.reset.side_effect = git.exc.GitCommandError(['reset'], 1)
        mock_repo.return_value = mock_repo_instance
        
        with self.assertLogs('tdac.core.git_manager', level='ERROR') as log:
            manager = GitManager()
            result = manager.revert_changes()
            
            mock_repo_instance.git.reset.assert_called_with('--hard')
            mock_repo_instance.git.clean.assert_not_called()
            self.assertFalse(result)
            self.assertIn("Error reverting changes", log.output[0])

if __name__ == '__main__':
    unittest.main()
