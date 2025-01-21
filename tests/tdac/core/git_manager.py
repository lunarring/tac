import git
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class GitManager:
    def __init__(self, repo_path: str = '.') -> None:
        """
        Initializes the GitManager with the specified repository path.
        """
        try:
            self.repo = git.Repo(repo_path)
            logger.debug(f"Git repository at '{repo_path}' initialized successfully.")
        except git.exc.InvalidGitRepositoryError:
            logger.error("Not a git repository. Please initialize git first.")
            self.repo = None
        except git.exc.GitCommandError as e:
            logger.error(f"Error initializing git repository: {e}")
            self.repo = None

    def check_status(self) -> bool:
        """
        Check if the git repository exists and the working tree is clean.

        Returns:
            bool: True if the working tree is clean, False otherwise.
        """
        if not self.repo:
            logger.debug("No repository to check status.")
            return False

        try:
            if self.repo.is_dirty(untracked_files=True):
                logger.error("Git working tree is not clean. Please commit or stash your changes before proceeding!")
                print("\nGit status:")
                print(self.repo.git.status())
                return False

            logger.debug("Git working tree is clean.")
            return True
        except git.exc.GitCommandError as e:
            logger.error(f"Error checking git status: {e}")
            return False

    def handle_post_execution(self, config: dict, commit_message: Optional[str] = None) -> bool:
        """
        Handle git operations after successful execution based on the configuration.

        Args:
            config (dict): Configuration dictionary containing git settings.
            commit_message (Optional[str]): Custom commit message.

        Returns:
            bool: True if operations succeed, False otherwise.
        """
        if not self.repo or not config.get('git', {}).get('auto_push', False):
            logger.debug("Git operations not required based on configuration.")
            return True

        try:
            # Stage all changes
            self.repo.git.add('.')
            logger.debug("Staged all changes.")

            # Generate commit message if not provided
            if not commit_message:
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
        except git.exc.GitCommandError as e:
            logger.error(f"Error during git operations: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during git operations: {e}")
            return False

    def revert_changes(self) -> bool:
        """
        Revert all changes and delete untracked files after a failed execution.

        Returns:
            bool: True if revert succeeds, False otherwise.
        """
        if not self.repo:
            logger.debug("No repository to revert changes.")
            return False

        try:
            # Revert all changes to the last commit
            self.repo.git.reset('--hard')
            logger.debug("Reset repository to the last commit.")

            # Clean untracked files and directories
            self.repo.git.clean('-fd')
            logger.debug("Cleaned untracked files and directories.")

            logger.info("Reverted all changes and cleaned untracked files.")
            return True
        except git.exc.GitCommandError as e:
            logger.error(f"Error reverting changes: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during reverting changes: {e}")
            return False
