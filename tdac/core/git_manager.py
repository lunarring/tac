import logging
import git
from git.exc import InvalidGitRepositoryError, GitCommandError

class GitManager:
    def __init__(self, repo_path='.'):
        self.logger = logging.getLogger('tdac.core.git_manager')
        try:
            self.repo = git.Repo(repo_path)
        except InvalidGitRepositoryError:
            self.logger.error("Not a git repository. Please initialize git first.")
            self.repo = None
        except GitCommandError as e:
            self.logger.error(f"Git command error during initialization: {e}")
            self.repo = None

    def check_status(self):
        if not self.repo:
            self.logger.error("No repository found.")
            return False
        try:
            is_dirty = self.repo.is_dirty(untracked_files=True)
            if is_dirty:
                status = self.repo.git.status()
                self.logger.error("Git working tree is not clean. Please commit or stash your changes before running TDAC!")
                self.logger.debug(f"Git status output:\n{status}")
                return False
            return True
        except GitCommandError as e:
            self.logger.error(f"Error checking git status: {e}")
            return False

    def handle_post_execution(self, config, commit_message=None):
        if not self.repo:
            return True
        auto_push = config.get('git', {}).get('auto_push', False)
        if not auto_push:
            return True
        try:
            self.repo.git.add('.')
            if commit_message:
                message = commit_message
            else:
                changed_files = self.repo.git.diff('--name-only').split('\n')
                if not changed_files:
                    message = "TDAC: No changes to commit."
                else:
                    file_list = ", ".join(changed_files[:-1])
                    if len(changed_files) > 2:
                        message = f"TDAC: Successfully implemented changes in {file_list} and {len(changed_files)-2} more files"
                    elif len(changed_files) == 2:
                        message = f"TDAC: Successfully implemented changes in {file_list}"
                    else:
                        message = f"TDAC: Successfully implemented changes in {changed_files[0]}"
            self.repo.git.commit('-m', message)
            self.repo.git.push()
            return True
        except GitCommandError as e:
            self.logger.error(f"Error during git operations: {e}")
            return False

    def revert_changes(self):
        """
        Revert all uncommitted changes in the repository.
        
        Returns:
            bool: True if reversion was successful, False otherwise.
        """
        if not self.repo:
            self.logger.error("No git repository found to revert changes.")
            return False
        try:
            self.repo.git.reset('--hard')
            self.repo.git.clean('-fd')
            self.logger.info("Successfully reverted all changes.")
            return True
        except GitCommandError as e:
            self.logger.error(f"Error reverting changes: {e}")
            return False
