import git
import os
import subprocess
import shutil
import tempfile
import difflib
from typing import Optional, Tuple, Union
from tac.core.log_config import setup_logging
from tac.core.config import config

logger = setup_logging('tac.utils.git_manager')

def create_git_manager(repo_path: str = '.', use_fake_git: bool = False) -> Union['GitManager', 'FakeGitManager']:
    """
    Factory function that creates and returns either a GitManager or FakeGitManager instance.
    
    Args:
        repo_path: Path to the repository
        use_fake_git: If True, always use FakeGitManager regardless of other conditions
        
    Returns:
        Either a GitManager or FakeGitManager instance
    """
    # Always use FakeGitManager if explicitly requested
    if use_fake_git:
        logger.info("Using FakeGitManager as explicitly requested")
        return FakeGitManager(repo_path)
        
    # Use FakeGitManager if git is disabled in config
    if not config.git.enabled:
        logger.info("Using FakeGitManager because git is disabled in config")
        return FakeGitManager(repo_path)
        
    # Try to initialize real GitManager
    try:
        # Check if git is available by trying to initialize a repo
        git_manager = GitManager(repo_path)
        
        # If initialization failed (repo is None), use FakeGitManager
        if git_manager.repo is None:
            logger.info("Using FakeGitManager because GitManager initialization failed")
            return FakeGitManager(repo_path)
        
        # Otherwise, use the real GitManager
        logger.info(f"Using real GitManager with repository at {repo_path}")
        return git_manager
        
    except Exception as e:
        # If any exception occurs during GitManager initialization, use FakeGitManager
        logger.warning(f"Error initializing GitManager: {e}. Falling back to FakeGitManager")
        return FakeGitManager(repo_path)

class GitManager:
    def __init__(self, repo_path: str = '.'):
        # Check if git is enabled in config
        if not config.git.enabled:
            logger.info("Git operations are disabled in config.")
            self.repo = None
            self.base_branch = None
            return

        try:
            self.repo = git.Repo(repo_path)
            self.base_branch = self.get_current_branch()
            logger.debug(f"Git repository initialized successfully at {repo_path} with base branch {self.base_branch}.")
            self.ensure_gitignore_includes_tac()
        except git.exc.InvalidGitRepositoryError:
            logger.warning("Not a git repository. Please initialize git first.")
            self.repo = None
            self.base_branch = None
        except git.exc.GitCommandError as e:
            logger.warning(f"Error initializing git repository: {e}")
            self.repo = None
            self.base_branch = None

    def get_current_branch(self) -> Optional[str]:
        """Get the name of the current branch using git rev-parse --abbrev-ref HEAD"""
        if not config.git.enabled:
            logger.debug("Git operations are disabled.")
            return None
            
        if not self.repo or not self.repo.working_dir:
            return None
        try:
            branch = subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self.repo.working_dir,
                encoding="utf-8"
            ).strip()
            return branch
        except Exception as e:
            logger.error(f"Error detecting branch: {e}")
            return None

    def get_complete_diff(self) -> str:
        """
        Get a complete diff of the current state, including:
        - All staged changes
        - All unstaged changes
        - List of untracked files with their contents
        
        Returns:
            str: A formatted string containing all relevant diffs and file lists
        """
        if not config.git.enabled:
            logger.debug("Git operations are disabled.")
            return "Git operations are disabled"
            
        if not self.repo:
            return "Git repository not available"
            
        try:
            git_diff = []
            
            # Get complete diff output for staged changes
            try:
                staged_diff = self.repo.git.diff('--staged', '--full-index')
                if staged_diff:
                    git_diff.append("=== Staged Changes ===")
                    git_diff.append(staged_diff)
                    git_diff.append("")  # Empty line for separation
            except git.exc.GitCommandError as e:
                git_diff.append(f"Error getting staged changes: {str(e)}")

            # Get complete diff output for unstaged changes
            try:
                unstaged_diff = self.repo.git.diff('--full-index')
                if unstaged_diff:
                    git_diff.append("=== Unstaged Changes ===")
                    git_diff.append(unstaged_diff)
                    git_diff.append("")  # Empty line for separation
            except git.exc.GitCommandError as e:
                git_diff.append(f"Error getting unstaged changes: {str(e)}")
            
            # Get untracked files with contents
            untracked = self.repo.untracked_files
            if untracked:
                git_diff.append("=== Untracked Files ===")
                for file in sorted(untracked):
                    git_diff.append(f"+ {file}")
                    try:
                        # Get absolute path by joining repo path with file path
                        file_path = os.path.join(self.repo.working_dir, file)
                        if os.path.exists(file_path):
                            with open(file_path, 'r', encoding='utf-8') as f:
                                content = f.read()
                            git_diff.append("File contents:")
                            git_diff.append("```")
                            git_diff.append(content)
                            git_diff.append("```")
                    except Exception as e:
                        git_diff.append(f"Error reading file contents: {str(e)}")
                    git_diff.append("")  # Empty line for separation
            
            if not git_diff:
                return "No changes detected (working directory clean)"
                
            return "\n".join(git_diff)
            
        except Exception as e:
            return f"Failed to get git diff: {str(e)}"

    def check_status(self, ignore_untracked: bool = False) -> Tuple[bool, str]:
        """
        Check if git repo exists and working tree is clean.
        
        Args:
            ignore_untracked: If True, untracked files will not cause the status check to fail
            
        Returns:
            tuple: (success, current_branch)
        """
        if not config.git.enabled:
            logger.debug("Git operations are disabled.")
            return True, ""
            
        if not self.repo:
            logger.debug("No repository to check status.")
            return False, ""
            
        try:
            current_branch = self.get_current_branch() or ""
            
            # Check if working tree is dirty, respecting ignore_untracked parameter
            if ignore_untracked:
                is_dirty = self.repo.is_dirty(untracked_files=False)  # Only check tracked files
            else:
                is_dirty = self.repo.is_dirty(untracked_files=True)  # Check all files
                
            if is_dirty:
                logger.error("Git working tree is not clean. Please commit or stash your changes before running TAC!")
                logger.error("\nGit status:")
                logger.error(self.repo.git.status())
                return False, current_branch
                
            logger.debug("Git working tree is clean.")
            return True, current_branch
            
        except git.exc.GitCommandError as e:
            logger.error(f"Error checking git status: {e}")
            return False, ""

    def handle_post_execution(self, config: dict, commit_message: str) -> bool:
        """Handle git operations after successful block execution"""
        if not config.get('git', {}).get('enabled', True):
            logger.debug("Git operations are disabled.")
            return True
            
        if not self.repo or not config.get('git', {}).get('auto_commit_if_success', False):
            logger.debug("Git operations not required based on configuration.")
            return True

        try:
            # Stage all changes including untracked files
            self.repo.git.add('--all')
            logger.debug("Staged all changes including untracked files.")

            try:
                # Get status before commit
                status_before = self.repo.git.status()
                logger.debug(f"Git status before commit:\n{status_before}")

                # Commit changes and capture output
                commit_output = self.repo.git.commit('-m', commit_message)
                logger.debug(f"Git commit output:\n{commit_output}")

                # Get status after commit to verify
                status_after = self.repo.git.status()
                logger.debug(f"Git status after commit:\n{status_after}")

                logger.debug("Committed all changes successfully.")
            except git.exc.GitCommandError as commit_error:
                # Check if the error is actually indicating success
                if "nothing to commit" in str(commit_error):
                    logger.info("Nothing to commit - working tree clean")
                    return True
                elif commit_error.status == 1 and "On branch" in str(commit_error):
                    # This might be the case where commit succeeded but git returns 1
                    logger.debug("Commit might have succeeded despite error code 1")
                    return True
                else:
                    raise commit_error  # Re-raise if it's a real error

            logger.info(f"Successfully committed changes. Commit message: {commit_message}")
            current_branch = self.get_current_branch()
            base_branch = self.base_branch if self.base_branch else "main"
            
            # Push changes if configured
            if config.get('git', {}).get('auto_push_if_success', False):
                try:
                    self.repo.git.push('origin', current_branch)
                    logger.info(f"Successfully pushed changes to origin/{current_branch}")
                except git.exc.GitCommandError as e:
                    logger.error(f"Failed to push changes: {e}")
                    # Continue execution even if push fails
            
            github_url = self.get_github_web_url()
            pr_url = f"{github_url}/pull/new/{current_branch}" if github_url else "https://github.com/<owner>/<repo>/pull/new/{current_branch}"
            
            # Print manual git commands with more visibility
            logger.info("="*80)
            logger.info(f"✅ Changes successfully committed to branch '{current_branch}'")
            logger.info("="*80)
            logger.info("📋 Manual Git Commands:")
            logger.info(f"  To merge these changes from the terminal:")
            logger.info(f"    git switch {base_branch} && git merge {current_branch}")
            logger.info(f"  To merge and delete the branch after:")
            logger.info(f"    git switch {base_branch} && git merge {current_branch} && git branch -D {current_branch}")
            logger.info(f"  To create a pull request:")
            logger.info(f"    {pr_url}")
            logger.info("="*80)
            
            return True
        except Exception as e:
            logger.error(f"Error during git operations: {e}")
            if hasattr(e, 'stdout'):
                logger.error(f"Command stdout: {e.stdout}")
            if hasattr(e, 'stderr'):
                logger.error(f"Command stderr: {e.stderr}")
            return False

    def revert_changes(self) -> bool:
        """Stash all changes and delete untracked files after failed execution"""
        if not config.git.enabled:
            logger.debug("Git operations are disabled.")
            return True
            
        if not self.repo:
            logger.debug("No repository to revert changes.")
            return False

        try:
            current_branch = self.get_current_branch()
            base_branch = self.base_branch if self.base_branch else "main"
            
            # Stash all changes including untracked files
            self.repo.git.stash('push', '--include-untracked')
            logger.debug("Stashed all changes including untracked files.")

            # Clean any remaining untracked files and directories
            self.repo.git.clean('-fd')
            logger.debug("Cleaned untracked files and directories.")

            logger.info("Successfully stashed all changes and cleaned working directory")
            
            # Print manual cleanup instructions
            logger.info("="*80)
            logger.info("🔄 Attempt failed - Changes have been stashed")
            logger.info("="*80)
            logger.info("📋 Manual Git Cleanup Commands (if needed):")
            logger.info(f"  To switch back to your main branch and clean up:")
            logger.info(f"    git switch {base_branch} && git restore . && git clean -fd && git branch -D {current_branch}")
            logger.info("="*80)
            
            return True
        except Exception as e:
            logger.error(f"Error reverting changes: {e}")
            
            # Even if automatic reversion fails, provide manual instructions
            current_branch = self.get_current_branch() or "current_branch"
            base_branch = self.base_branch if self.base_branch else "main"
            
            logger.error("="*80)
            logger.error("❌ Failed to automatically revert changes")
            logger.error("="*80)
            logger.error("📋 Manual Git Cleanup Commands:")
            logger.error(f"  To switch back to your main branch and clean up:")
            logger.error(f"    git switch {base_branch} && git restore . && git clean -fd && git branch -D {current_branch}")
            logger.error("="*80)
            
            return False

    def create_or_switch_to_tac_branch(self, tac_id: str) -> bool:
        """Create or switch to a TAC branch with the given tac_id, regardless of current branch state."""
        if not config.git.enabled:
            logger.debug("Git operations are disabled.")
            return True
            
        if not self.repo:
            logger.error("No git repository available")
            return False

        current_branch = self.get_current_branch()
        if current_branch.startswith("tac_"):
            logger.info(f"Already on a TAC branch: {current_branch}. Retaining current branch.")
            return True

        try:
            branches = [b.name for b in self.repo.branches]
            if tac_id in branches:
                self.repo.git.checkout(tac_id)
                logger.info(f"Switched to existing TAC branch: {tac_id}")
            else:
                self.repo.git.checkout('-b', tac_id)
                logger.info(f"Created and checked out new TAC branch: {tac_id}")
            return True
        except git.exc.GitCommandError as e:
            logger.error(f"Failed to create or switch to TAC branch {tac_id}: {e}")
            return False

    def checkout_branch(self, branch_name: str, create: bool = False) -> bool:
        """Checkout an existing branch or create a new one if it doesn't exist.
        
        Args:
            branch_name: Name of the branch to checkout
            create: If True, create the branch if it doesn't exist
            
        Returns:
            bool: True if checkout was successful, False otherwise
        """
        if not config.git.enabled:
            logger.debug("Git operations are disabled.")
            return True
            
        if not self.repo:
            logger.error("No git repository available")
            return False
            
        try:
            # Check if branch exists
            branches = [b.name for b in self.repo.branches]
            if branch_name in branches:
                self.repo.git.checkout(branch_name)
                logger.info(f"Switched to existing branch: {branch_name}")
            elif create:
                self.repo.git.checkout('-b', branch_name)
                logger.info(f"Created and checked out new branch: {branch_name}")
            else:
                logger.error(f"Branch {branch_name} does not exist and create=False")
                return False
            return True
        except git.exc.GitCommandError as e:
            logger.error(f"Failed to checkout branch {branch_name}: {e}")
            return False

    def commit(self, commit_message: str) -> bool:
        """Commit all changes with the given message.
        
        Args:
            commit_message: Message for the commit
            
        Returns:
            bool: True if commit was successful, False otherwise
        """
        if not config.git.enabled:
            logger.debug("Git operations are disabled.")
            return True
            
        if not self.repo:
            logger.error("No git repository available")
            return False
            
        try:
            # Stage all changes
            self.repo.git.add('--all')
            logger.debug("Staged all changes")
            
            # Commit changes
            try:
                self.repo.git.commit('-m', commit_message)
                logger.info(f"Committed changes with message: {commit_message}")
                return True
            except git.exc.GitCommandError as commit_error:
                # Check if the error is actually indicating success
                if "nothing to commit" in str(commit_error):
                    logger.info("Nothing to commit - working tree clean")
                    return True
                else:
                    raise commit_error
        except Exception as e:
            logger.error(f"Failed to commit changes: {e}")
            return False

    def get_github_web_url(self) -> str:
        """Get the GitHub web URL for the repository"""
        try:
            remote_url = self.repo.remotes.origin.url
            # Handle SSH or HTTPS URLs
            if remote_url.startswith('git@github.com:'):
                # Convert SSH URL to HTTPS format
                repo_path = remote_url.split('git@github.com:')[1].rstrip('.git')
            elif remote_url.startswith('https://github.com/'):
                repo_path = remote_url.split('https://github.com/')[1].rstrip('.git')
            else:
                return None
            return f"https://github.com/{repo_path}"
        except Exception as e:
            logger.error(f"Error getting GitHub URL: {e}")
            return None

    def ensure_gitignore_includes_tac(self):
        """Ensure that the .gitignore file in the repository's working directory includes the '.tac_*' exclusion pattern.
        If the pattern is missing, append it automatically and log a warning. Also commit the update if made."""
        if not config.git.enabled:
            logger.debug("Git operations are disabled.")
            return
            
        if not self.repo or not self.repo.working_dir:
            return
        gitignore_path = os.path.join(self.repo.working_dir, ".gitignore")
        pattern = ".tac_*"
        commit_required = False
        try:
            if os.path.exists(gitignore_path):
                with open(gitignore_path, "r+", encoding="utf-8") as f:
                    contents = f.read()
                    if pattern not in contents:
                        f.write("\n" + pattern + "\n")
                        logger.warning(f"'.gitignore' was missing '{pattern}' exclusion. The pattern has been automatically appended.")
                        commit_required = True
            else:
                with open(gitignore_path, "w", encoding="utf-8") as f:
                    f.write(pattern + "\n")
                logger.warning(f"'.gitignore' file did not exist. Created new file with '{pattern}' exclusion.")
                commit_required = True
            if commit_required:
                try:
                    self.repo.git.add(".gitignore")
                    self.repo.git.commit("-m", "Update .gitignore to include '.tac_*' exclusion")
                    logger.info("Committed updated .gitignore")
                except Exception as commit_err:
                    logger.error(f"Failed to commit .gitignore update: {commit_err}")
        except Exception as e:
            logger.error(f"Error ensuring gitignore includes '{pattern}': {e}")

    def restore_commit(self, commit_name: str) -> bool:
        """
        Restore the codebase to a specific commit state.
        
        Args:
            commit_name: Name of the commit to restore to
            
        Returns:
            bool: True if restoration was successful, False otherwise
        """
        if commit_name not in self.commits:
            logger.error(f"Commit '{commit_name}' not found")
            return False
            
        try:
            # Get the files from the commit
            commit_files = self.commits[commit_name]
            
            # Determine if this is an original or optimized version
            is_original = commit_name == "original_state_before_optimization"
            action_verb = "Restoring" if is_original else "Applying"
            file_action = "to original state" if is_original else "optimized version"
            
            logger.info(f"{action_verb} files {file_action} ({commit_name})")
            
            # Restore each file to its state in the commit
            files_processed = 0
            for rel_path, content in commit_files.items():
                # Restore in the temporary directory
                temp_path = os.path.join(self.temp_dir, rel_path)
                
                # Create directory if it doesn't exist
                os.makedirs(os.path.dirname(temp_path), exist_ok=True)
                
                # Write content back to the file in temp dir
                with open(temp_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                # Also restore in the original repository
                orig_path = os.path.join(self.repo_path, rel_path)
                try:
                    # Ensure the directory exists
                    os.makedirs(os.path.dirname(orig_path), exist_ok=True)
                    
                    # Write content back to the original file
                    with open(orig_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    
                    files_processed += 1
                    # Only log at debug level to avoid flooding the console
                    if is_original:
                        logger.debug(f"Restored file to original state: {rel_path}")
                    else:
                        logger.debug(f"Applied optimized version to file: {rel_path}")
                        
                except Exception as e:
                    action = "restoring" if is_original else "applying optimization to"
                    logger.error(f"Error {action} file {rel_path}: {e}")
                    # Continue with other files even if one fails
            
            # Remove any files that don't exist in the commit from the temp directory
            for root, _, files in os.walk(self.temp_dir):
                if any(part.startswith('.') for part in root.split(os.sep)):
                    continue
                    
                for file in files:
                    _, ext = os.path.splitext(file)
                    if ext.lower() not in self.code_file_extensions:
                        continue
                        
                    temp_path = os.path.join(root, file)
                    rel_path = os.path.relpath(temp_path, self.temp_dir)
                    
                    if rel_path not in commit_files:
                        # Remove file that doesn't exist in the commit
                        os.remove(temp_path)
                        
                        # Also remove from original repository if it exists
                        orig_path = os.path.join(self.repo_path, rel_path)
                        if os.path.exists(orig_path):
                            try:
                                os.remove(orig_path)
                                logger.debug(f"Removed file: {rel_path}")
                            except Exception as e:
                                logger.error(f"Error removing file {rel_path}: {e}")
            
            # Update original_files to match the commit state
            self.original_files = commit_files.copy()
            
            if is_original:
                logger.info(f"Successfully restored {files_processed} files to original state")
            else:
                logger.info(f"Successfully applied optimized version: {commit_name} ({files_processed} files updated)")
                
            return True
        except Exception as e:
            action = "restoring to original state" if commit_name == "original_state_before_optimization" else "applying optimized version"
            logger.error(f"Error {action}: {e}")
            return False

class FakeGitManager:
    """
    A minimalistic fake Git manager that simulates basic Git operations without requiring an actual Git repository.
    Only implements the core methods needed for simple version tracking.
    """
    
    def __init__(self, repo_path: str = '.', cleanup_temp_dir: bool = True):
        """
        Initialize the FakeGitManager.
        
        Args:
            repo_path: Path to the original repository
            cleanup_temp_dir: Whether to automatically clean up the temp directory when done (default: True)
        """
        self.repo_path = os.path.abspath(repo_path)
        self.temp_dir = tempfile.mkdtemp(prefix="fake_git_")
        self.commits = {}  # Store commits by name
        self.cleanup_temp_dir = cleanup_temp_dir
        self.current_commit = None  # Track the current commit
        self.base_branch = "main"  # Default base branch
        
        # File extensions to consider as programming-relevant
        self.code_file_extensions = [
            '.py', '.js', '.jsx', '.ts', '.tsx', '.html', '.css', '.scss', 
            '.java', '.c', '.cpp', '.h', '.hpp', '.cs', '.go', '.rs', '.rb', 
            '.php', '.swift', '.kt', '.sh', '.bash', '.json', '.yml', '.yaml', 
            '.md', '.txt', '.sql'
        ]
        
        logger.info(f"Initialized FakeGitManager with repo path: {self.repo_path}")
        logger.info(f"Using temporary directory: {self.temp_dir}")

        self.commit("initial_commit")
    
    def _get_files_from_repo(self):
        """Get all programming-relevant files from the original repository."""
        files = {}
        
        if not os.path.exists(self.repo_path):
            logger.error(f"Repository path does not exist: {self.repo_path}")
            return files
            
        logger.info(f"Reading files from repository: {self.repo_path}")
        
        for root, _, file_list in os.walk(self.repo_path):
            # Skip hidden directories (like .git)
            if any(part.startswith('.') for part in root.split(os.sep)):
                continue
                
            for file in file_list:
                # Only include files with code extensions
                _, ext = os.path.splitext(file)
                if ext.lower() not in self.code_file_extensions:
                    continue
                    
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, self.repo_path)
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        files[rel_path] = content
                except Exception as e:
                    logger.error(f"Error reading file {file_path}: {e}")
        
        return files
    
    def _get_commit_dir(self, commit_msg):
        """Get the directory path for a specific commit."""
        return os.path.join(self.temp_dir, commit_msg)
    
    def commit(self, commit_msg: str) -> bool:
        """
        Create a new commit by copying all programming-relevant files into temp/commit_message.
        
        Args:
            commit_msg: Message/name for this commit
            
        Returns:
            bool: True if commit was successful, False otherwise
        """
        try:
            # Create a directory for this commit
            commit_dir = self._get_commit_dir(commit_msg)
            os.makedirs(commit_dir, exist_ok=True)
            
            # Get all current files from the repository
            current_files = self._get_files_from_repo()
            
            # Store this commit
            self.commits[commit_msg] = current_files
            self.current_commit = commit_msg
            
            # Copy files to the commit directory
            for rel_path, content in current_files.items():
                file_path = os.path.join(commit_dir, rel_path)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            
            logger.info(f"Created commit: {commit_msg} with {len(current_files)} files")
            return True
        except Exception as e:
            logger.error(f"Error creating commit: {e}")
            return False
    
    def restore_commit(self, commit_msg: str) -> bool:
        """
        Restore the commit_msg version completely.
        
        Args:
            commit_msg: Name of the commit to restore to
            
        Returns:
            bool: True if restoration was successful, False otherwise
        """
        if commit_msg not in self.commits:
            logger.error(f"Commit '{commit_msg}' not found")
            return False
            
        try:
            # Get the files from the commit
            commit_files = self.commits[commit_msg]
            
            logger.info(f"Restoring to commit: {commit_msg}")
            
            # Restore each file to its state in the commit
            for rel_path, content in commit_files.items():
                # Restore in the original repository
                orig_path = os.path.join(self.repo_path, rel_path)
                
                # Create directory if it doesn't exist
                os.makedirs(os.path.dirname(orig_path), exist_ok=True)
                
                # Write content back to the file
                with open(orig_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            
            # Remove files in repo that don't exist in the commit
            for root, _, files in os.walk(self.repo_path):
                # Skip hidden directories (like .git)
                if any(part.startswith('.') for part in root.split(os.sep)):
                    continue
                    
                for file in files:
                    # Only consider files with code extensions
                    _, ext = os.path.splitext(file)
                    if ext.lower() not in self.code_file_extensions:
                        continue
                        
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, self.repo_path)
                    
                    if rel_path not in commit_files:
                        try:
                            os.remove(file_path)
                            logger.debug(f"Removed file not in commit: {rel_path}")
                        except Exception as e:
                            logger.error(f"Error removing file {rel_path}: {e}")
            
            self.current_commit = commit_msg
            logger.info(f"Successfully restored to commit: {commit_msg}")
            return True
        except Exception as e:
            logger.error(f"Error restoring commit: {e}")
            return False
    
    def get_complete_diff(self, commit_msg: str = "initial_commit") -> str:
        """
        Get the complete diff in a git similar fashion between the current commit and the one specified in commit_msg.
        
        Args:
            commit_msg: Name of the commit to compare against (optional)
            
        Returns:
            str: A formatted string containing all relevant diffs
        """
            
        if commit_msg not in self.commits:
            return f"Error: Commit '{commit_msg}' not found"
            
        try:
            # Get the files from the specified commit
            commit_files = self.commits[commit_msg]
            
            # Get current files from the repository
            current_files = self._get_files_from_repo()
            
            git_diff = []
            
            # Check for modified and deleted files
            for rel_path, commit_content in commit_files.items():
                if rel_path not in current_files:
                    git_diff.append(f"=== Deleted File: {rel_path} ===")
                    git_diff.append(f"- {rel_path}")
                    git_diff.append("")
                    continue
                
                current_content = current_files[rel_path]
                
                if current_content != commit_content:
                    git_diff.append(f"=== Modified File: {rel_path} ===")
                    
                    # Generate a simple diff
                    commit_lines = commit_content.splitlines()
                    current_lines = current_content.splitlines()
                    
                    # Use difflib to get a unified diff
                    diff = difflib.unified_diff(
                        commit_lines,
                        current_lines,
                        fromfile=f'a/{rel_path}',
                        tofile=f'b/{rel_path}',
                        lineterm=''
                    )
                    
                    git_diff.extend(diff)
                    git_diff.append("")
            
            # Check for new files
            for rel_path in current_files:
                if rel_path not in commit_files:
                    git_diff.append(f"=== New File: {rel_path} ===")
                    git_diff.append(f"+ {rel_path}")
                    
                    # Show the content of the new file
                    content_lines = current_files[rel_path].splitlines()
                    for line in content_lines:
                        git_diff.append(f"+ {line}")
                    
                    git_diff.append("")
            
            if not git_diff:
                return "No differences found"
                
            return "\n".join(git_diff)
        except Exception as e:
            logger.error(f"Error generating diff: {e}")
            return f"Error generating diff: {str(e)}"
    
    def get_github_web_url(self) -> str:
        """Fake implementation of get_github_web_url"""
        logger.info("FakeGitManager: get_github_web_url called")
        return None
    
    def get_current_branch(self) -> Optional[str]:
        """Fake implementation of get_current_branch"""
        logger.info("FakeGitManager: get_current_branch called")
        return "main"
    
    def check_status(self, ignore_untracked: bool = False) -> Tuple[bool, str]:
        """Fake implementation of check_status"""
        logger.info("FakeGitManager: check_status called")
        return True, "main"
    
    def create_or_switch_to_tac_branch(self, tac_id: str) -> bool:
        """Fake implementation of create_or_switch_to_tac_branch"""
        logger.info(f"FakeGitManager: create_or_switch_to_tac_branch called with tac_id={tac_id}")
        return True
    
    def checkout_branch(self, branch_name: str, create: bool = False) -> bool:
        """Fake implementation of checkout_branch"""
        logger.info(f"FakeGitManager: checkout_branch called with branch_name={branch_name}, create={create}")
        return True
    
    def handle_post_execution(self, config: dict, commit_message: str) -> bool:
        """Fake implementation of handle_post_execution"""
        logger.info(f"FakeGitManager: handle_post_execution called with commit_message={commit_message}")
        return True
    
    def revert_changes(self) -> bool:
        """Fake implementation of revert_changes that restores to the first commit"""
        logger.info("FakeGitManager: revert_changes called")
        
        # If we have any commits, restore to the first one
        if self.commits:
            # Get the first commit (assuming the first one added is the initial one)
            first_commit = next(iter(self.commits))
            logger.info(f"FakeGitManager: Restoring to first commit: {first_commit}")
            return self.restore_commit(first_commit)
        
        logger.info("FakeGitManager: No commits to revert to")
        return True
    
    def __del__(self):
        """Clean up temporary directory when the object is garbage collected."""
        if self.cleanup_temp_dir and hasattr(self, 'temp_dir') and self.temp_dir and os.path.exists(self.temp_dir):
            try:
                logger.info(f"Cleaning up temporary directory: {self.temp_dir}")
                shutil.rmtree(self.temp_dir)
                self.temp_dir = None
            except Exception as e:
                logger.warning(f"Failed to clean up temporary directory: {str(e)}")
        elif not self.cleanup_temp_dir and hasattr(self, 'temp_dir') and self.temp_dir:
            logger.info(f"Keeping temporary directory for inspection: {self.temp_dir}")

# Example usage
if __name__ == "__main__":
    # Create a simple example project
    example_dir = tempfile.mkdtemp(prefix="example_project_")
    
    try:
        # Create some example files
        with open(os.path.join(example_dir, "main.py"), "w") as f:
            f.write("def hello():\n    print('Hello, world!')\n\nif __name__ == '__main__':\n    hello()")
        
        with open(os.path.join(example_dir, "utils.py"), "w") as f:
            f.write("def add(a, b):\n    return a + b")
        
        # Initialize the FakeGitManager with our example project - don't clean up temp dir
        git_manager = FakeGitManager(example_dir, cleanup_temp_dir=False)
        
        # Create initial commit
        git_manager.commit("initial_commit")
        
        # Make some changes
        with open(os.path.join(example_dir, "main.py"), "w") as f:
            f.write("def hello():\n    print('Hello, Git!')\n\nif __name__ == '__main__':\n    hello()")
        
        with open(os.path.join(example_dir, "config.py"), "w") as f:
            f.write("DEBUG = True\nVERSION = '1.0.0'")
        
        # Commit the changes
        git_manager.commit("add_config_update_main")
        
        # Show the diff between current state and initial commit
        diff = git_manager.get_complete_diff("initial_commit")
        print("\nDiff between current state and initial commit:")
        print(diff)
        
        # Restore to initial commit
        git_manager.restore_commit("initial_commit")
        
        # Verify restoration by checking diff (should be empty)
        diff_after_restore = git_manager.get_complete_diff("initial_commit")
        print("\nDiff after restore (should be empty):")
        print(diff_after_restore)
        
        # Print the temp directory path for inspection
        print(f"\nTemporary directory for inspection: {git_manager.temp_dir}")
        
    finally:
        # Clean up the example project directory, but not the git manager temp dir
        pass
        # if os.path.exists(example_dir):
        #     shutil.rmtree(example_dir)
    
