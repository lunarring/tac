import git
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

class GitManager:
    def __init__(self, repo_path: str = '.'):
        try:
            self.repo = git.Repo(repo_path)
            logger.debug(f"Git repository initialized successfully at {repo_path}.")
        except git.exc.InvalidGitRepositoryError:
            logger.error("Not a git repository. Please initialize git first.")
            self.repo = None
        except git.exc.GitCommandError as e:
            logger.error(f"Error initializing git repository: {e}")
            self.repo = None

    def get_complete_diff(self) -> str:
        """
        Get a complete diff of the current state, including:
        - Staged changes compared to HEAD
        - Unstaged changes
        - Last commit changes if no current changes
        
        Returns:
            str: A formatted string containing all relevant diffs
        """
        if not self.repo:
            return "Git repository not available"
            
        try:
            # Get complete diff including staged and working tree changes compared to HEAD
            try:
                # First, get the diff of staged changes compared to HEAD
                staged_diff = self.repo.git.diff('HEAD', '--staged')
                # Then get the diff of working tree compared to index
                unstaged_diff = self.repo.git.diff()
                
                # Combine both diffs with headers
                git_diff = ""
                if staged_diff:
                    git_diff += "=== Staged Changes (compared to HEAD) ===\n" + staged_diff + "\n"
                if unstaged_diff:
                    git_diff += "=== Unstaged Changes ===\n" + unstaged_diff
                
                # If no changes detected, try to get the diff of the last commit
                if not git_diff and self.repo.head.is_valid():
                    try:
                        last_commit_diff = self.repo.git.show('HEAD', '--patch')
                        git_diff = "=== Last Commit Changes ===\n" + last_commit_diff
                    except git.exc.GitCommandError:
                        git_diff = "No changes detected in last commit"
            except git.exc.GitCommandError as e:
                git_diff = f"Failed to get git diff: {str(e)}"
                
            return git_diff
        except Exception as e:
            return f"Failed to get git diff: {str(e)}"

    def check_status(self) -> bool:
        """Check if git repo exists and working tree is clean"""
        if not self.repo:
            logger.debug("No repository to check status.")
            return False
            
        try:
            if self.repo.is_dirty(untracked_files=True):
                logger.error("Git working tree is not clean. Please commit or stash your changes before running TDAC!")
                print("\nGit status:")
                print(self.repo.git.status())
                return False
                
            logger.debug("Git working tree is clean.")
            return True
        except git.exc.GitCommandError as e:
            logger.error(f"Error checking git status: {e}")
            return False

    def handle_post_execution(self, config: dict, commit_message: Optional[str] = None) -> bool:
        """Handle git operations after successful block execution"""
        if not self.repo or not config.get('git', {}).get('auto_push', False):
            logger.debug("Git operations not required based on configuration.")
            return True

        try:
            # Stage all changes
            self.repo.git.add('.')
            logger.debug("Staged all changes.")

            # Generate commit message
            if not commit_message:
                # Fallback to auto-generated message
                changed_files = self.repo.git.diff('--staged', '--name-only').split('\n')
                files_summary = ', '.join(changed_files[:3])
                if len(changed_files) > 3:
                    files_summary += f" and {len(changed_files) - 3} more files"
                commit_message = f"TDAC: Successfully implemented changes in {files_summary}"
                logger.debug(f"Auto-generated commit message: {commit_message}")

            # Commit changes
            self.repo.git.commit('-m', commit_message)
            logger.debug("Committed changes.")

            # Push changes
            self.repo.git.push()
            logger.debug("Pushed changes to remote repository.")

            logger.info(f"Successfully committed and pushed changes. Commit message: {commit_message}")
            return True
        except Exception as e:
            logger.error(f"Error during git operations: {e}")
            return False

    def revert_changes(self) -> bool:
        """Revert all changes and delete untracked files after failed execution"""
        if not self.repo:
            logger.debug("No repository to revert changes.")
            return False

        try:
            # Revert all changes to last commit
            self.repo.git.reset('--hard')
            logger.debug("Reverted all changes to the last commit.")

            # Clean untracked files and directories
            self.repo.git.clean('-fd')
            logger.debug("Cleaned untracked files and directories.")

            logger.error("Reverted all changes and cleaned untracked files")
            return True
        except Exception as e:
            logger.error(f"Error reverting changes: {e}")
            return False
