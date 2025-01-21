import git
import logging
import os
from typing import Optional
from colorama import init, Fore, Style

init()  # Initialize colorama

logger = logging.getLogger(__name__)

class GitManager:
    def __init__(self):
        try:
            self.repo = git.Repo('.')
        except git.exc.InvalidGitRepositoryError:
            logger.error("Not a git repository. Please initialize git first.")
            self.repo = None
        except git.exc.GitCommandError as e:
            logger.error(f"Error initializing git repository: {e}")
            self.repo = None

    def check_status(self) -> bool:
        """Check if git repo exists and working tree is clean"""
        if not self.repo:
            return False
            
        try:
            if self.repo.is_dirty(untracked_files=True):
                logger.error("Git working tree is not clean. Please commit or stash your changes before running TDAC!")
                print("\nGit status:")
                print(self.repo.git.status())
                return False
                
            return True
        except git.exc.GitCommandError as e:
            logger.error(f"Error checking git status: {e}")
            return False

    def handle_post_execution(self, config: dict, commit_message: Optional[str] = None) -> bool:
        """Handle git operations after successful block execution"""
        if not self.repo or not config.get('git', {}).get('auto_push', False):
            return True

        try:
            # Stage all changes
            self.repo.git.add('.')
            
            # Generate commit message
            if not commit_message:
                # Fallback to auto-generated message
                changed_files = self.repo.git.diff('--staged', '--name-only').split('\n')
                files_summary = ', '.join(changed_files[:3])
                if len(changed_files) > 3:
                    files_summary += f" and {len(changed_files) - 3} more files"
                commit_message = f"TDAC: Successfully implemented changes in {files_summary}"
            
            # Commit changes
            self.repo.git.commit('-m', commit_message)
            
            # Push changes
            self.repo.git.push()
            
            logger.info("Successfully committed and pushed changes")
            return True
        except Exception as e:
            logger.error(f"Error during git operations: {e}")
            return False

    def revert_changes(self) -> bool:
        """Revert all changes and delete untracked files after failed execution"""
        if not self.repo:
            return False

        try:
            # Revert all changes to last pushed commit
            self.repo.git.restore('--source=@{u}', '--staged', '--worktree', '.')
            
            # Clean untracked files and directories
            self.repo.git.clean('-fd')
            
            logger.info(f"{Fore.RED}Reverted all changes and cleaned untracked files{Style.RESET_ALL}")
            return True
        except Exception as e:
            logger.error(f"Error reverting changes: {e}")
            return False 