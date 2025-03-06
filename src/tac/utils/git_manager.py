import git
import os
import subprocess
import shutil
import tempfile
from typing import Optional, Tuple
from tac.core.log_config import setup_logging
from tac.core.config import config

logger = setup_logging('tac.utils.git_manager')

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
            logger.error("Not a git repository. Please initialize git first.")
            self.repo = None
            self.base_branch = None
        except git.exc.GitCommandError as e:
            logger.error(f"Error initializing git repository: {e}")
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
    A fake Git manager that simulates key Git operations without requiring an actual Git repository.
    This is useful for performance testing where we want to work with a temporary copy of the codebase.
    
    The FakeGitManager mirrors the GitManager interface but operates on a temporary directory
    containing copies of the original files rather than using actual Git commands.
    
    Can be used as a context manager to automatically clean up the temporary directory:
    
    ```python
    with FakeGitManager.for_performance_testing() as git_manager:
        # Use git_manager
        # Temporary directory will be automatically cleaned up when exiting the with block
    ```
    """
    
    def __init__(self, repo_path: str = '.', temp_dir: str = None):
        """
        Initialize the FakeGitManager.
        
        Args:
            repo_path: Path to the original repository
            temp_dir: Path to the temporary directory where files will be copied
        """
        self.repo_path = os.path.abspath(repo_path)
        self.temp_dir = temp_dir
        self.original_files = {}  # Store original file contents for reverting
        self.base_branch = "fake_main"
        self.current_branch = "fake_main"
        self.code_file_extensions = [
            '.py', '.js', '.jsx', '.ts', '.tsx', '.html', '.css', '.scss', 
            '.java', '.c', '.cpp', '.h', '.hpp', '.cs', '.go', '.rs', '.rb', 
            '.php', '.swift', '.kt', '.sh', '.bash', '.json', '.yml', '.yaml', 
            '.md', '.txt', '.sql'
        ]
        
        # Store commits by name for later restoration
        self.commits = {}
        
        logger.info(f"Initialized FakeGitManager with repo path: {self.repo_path}")
        if self.temp_dir:
            logger.info(f"Using temporary directory: {self.temp_dir}")
            self._copy_code_files()
    
    def __enter__(self):
        """Context manager entry point."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit point - clean up temporary directory."""
        self.cleanup()
        return False  # Don't suppress exceptions
    
    def cleanup(self):
        """Clean up resources used by the FakeGitManager."""
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                logger.info(f"Cleaning up temporary directory: {self.temp_dir}")
                shutil.rmtree(self.temp_dir)
                self.temp_dir = None
            except Exception as e:
                logger.warning(f"Failed to clean up temporary directory: {str(e)}")
    
    def _copy_code_files(self):
        """Copy all code files from the original repository to the temporary directory."""
        if not self.temp_dir or not os.path.exists(self.repo_path):
            return
            
        logger.info(f"Copying code files from {self.repo_path} to {self.temp_dir}")
        
        for root, _, files in os.walk(self.repo_path):
            # Skip hidden directories (like .git)
            if any(part.startswith('.') for part in root.split(os.sep)):
                continue
                
            for file in files:
                # Only copy files with code extensions
                _, ext = os.path.splitext(file)
                if ext.lower() not in self.code_file_extensions:
                    continue
                    
                src_path = os.path.join(root, file)
                # Create relative path from repo_path
                rel_path = os.path.relpath(src_path, self.repo_path)
                dst_path = os.path.join(self.temp_dir, rel_path)
                
                # Create destination directory if it doesn't exist
                os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                
                try:
                    # Copy the file
                    shutil.copy2(src_path, dst_path)
                    
                    # Store original content for potential reversion
                    with open(src_path, 'r', encoding='utf-8') as f:
                        self.original_files[rel_path] = f.read()
                        
                except Exception as e:
                    logger.error(f"Error copying file {src_path}: {e}")
    
    def get_current_branch(self) -> Optional[str]:
        """Get the name of the current fake branch."""
        return self.current_branch
    
    def get_complete_diff(self) -> str:
        """
        Get a complete diff of the current state compared to the original files.
        
        Returns:
            str: A formatted string containing all relevant diffs
        """
        if not self.temp_dir:
            return "Temporary directory not available"
            
        try:
            git_diff = []
            
            # Compare each file in the temporary directory with its original
            for rel_path, original_content in self.original_files.items():
                temp_path = os.path.join(self.temp_dir, rel_path)
                
                if not os.path.exists(temp_path):
                    git_diff.append(f"=== Deleted File: {rel_path} ===")
                    git_diff.append(f"- {rel_path}")
                    git_diff.append("")
                    continue
                
                with open(temp_path, 'r', encoding='utf-8') as f:
                    current_content = f.read()
                
                if current_content != original_content:
                    git_diff.append(f"=== Modified File: {rel_path} ===")
                    
                    # Generate a simple diff
                    original_lines = original_content.splitlines()
                    current_lines = current_content.splitlines()
                    
                    # Use difflib to get a unified diff
                    import difflib
                    diff = difflib.unified_diff(
                        original_lines,
                        current_lines,
                        fromfile=f'a/{rel_path}',
                        tofile=f'b/{rel_path}',
                        lineterm=''
                    )
                    
                    git_diff.extend(diff)
                    git_diff.append("")
            
            # Check for new files
            for root, _, files in os.walk(self.temp_dir):
                if any(part.startswith('.') for part in root.split(os.sep)):
                    continue
                    
                for file in files:
                    _, ext = os.path.splitext(file)
                    if ext.lower() not in self.code_file_extensions:
                        continue
                        
                    temp_path = os.path.join(root, file)
                    rel_path = os.path.relpath(temp_path, self.temp_dir)
                    
                    if rel_path not in self.original_files:
                        git_diff.append(f"=== New File: {rel_path} ===")
                        git_diff.append(f"+ {rel_path}")
                        
                        try:
                            with open(temp_path, 'r', encoding='utf-8') as f:
                                content = f.read()
                            git_diff.append("File contents:")
                            git_diff.append("```")
                            git_diff.append(content)
                            git_diff.append("```")
                        except Exception as e:
                            git_diff.append(f"Error reading file contents: {str(e)}")
                            
                        git_diff.append("")
            
            if not git_diff:
                return "No changes detected"
                
            return "\n".join(git_diff)
            
        except Exception as e:
            return f"Failed to get diff: {str(e)}"
    
    def check_status(self, ignore_untracked: bool = False) -> Tuple[bool, str]:
        """
        Check if there are any changes in the temporary directory.
        
        Args:
            ignore_untracked: If True, new files will not cause the status check to fail
            
        Returns:
            tuple: (success, current_branch)
        """
        if not self.temp_dir:
            logger.debug("No temporary directory to check status.")
            return False, ""
            
        try:
            has_changes = False
            
            # Check for modified files
            for rel_path, original_content in self.original_files.items():
                temp_path = os.path.join(self.temp_dir, rel_path)
                
                if not os.path.exists(temp_path):
                    # File was deleted
                    has_changes = True
                    break
                
                with open(temp_path, 'r', encoding='utf-8') as f:
                    current_content = f.read()
                
                if current_content != original_content:
                    # File was modified
                    has_changes = True
                    break
            
            # Check for new files if not ignoring untracked
            if not ignore_untracked and not has_changes:
                for root, _, files in os.walk(self.temp_dir):
                    if any(part.startswith('.') for part in root.split(os.sep)):
                        continue
                        
                    for file in files:
                        _, ext = os.path.splitext(file)
                        if ext.lower() not in self.code_file_extensions:
                            continue
                            
                        temp_path = os.path.join(root, file)
                        rel_path = os.path.relpath(temp_path, self.temp_dir)
                        
                        if rel_path not in self.original_files:
                            # New file
                            has_changes = True
                            break
                    
                    if has_changes:
                        break
            
            if has_changes:
                logger.debug("Changes detected in the temporary directory.")
                return False, self.current_branch
                
            logger.debug("No changes detected in the temporary directory.")
            return True, self.current_branch
            
        except Exception as e:
            logger.error(f"Error checking status: {e}")
            return False, ""
    
    def revert_changes(self) -> bool:
        """Revert all changes in the temporary directory to the original state."""
        if not self.temp_dir:
            logger.debug("No temporary directory to revert changes.")
            return False

        try:
            # Restore all original files
            for rel_path, original_content in self.original_files.items():
                temp_path = os.path.join(self.temp_dir, rel_path)
                
                # Create directory if it doesn't exist
                os.makedirs(os.path.dirname(temp_path), exist_ok=True)
                
                # Write original content back to the file
                with open(temp_path, 'w', encoding='utf-8') as f:
                    f.write(original_content)
            
            # Remove any new files
            for root, _, files in os.walk(self.temp_dir):
                if any(part.startswith('.') for part in root.split(os.sep)):
                    continue
                    
                for file in files:
                    _, ext = os.path.splitext(file)
                    if ext.lower() not in self.code_file_extensions:
                        continue
                        
                    temp_path = os.path.join(root, file)
                    rel_path = os.path.relpath(temp_path, self.temp_dir)
                    
                    if rel_path not in self.original_files:
                        # Remove new file
                        os.remove(temp_path)
            
            logger.info("Successfully reverted all changes in the temporary directory.")
            return True
        except Exception as e:
            logger.error(f"Error reverting changes: {e}")
            return False
    
    def create_or_switch_to_tac_branch(self, tac_id: str) -> bool:
        """Simulate creating or switching to a TAC branch."""
        self.current_branch = tac_id
        logger.info(f"Switched to fake TAC branch: {tac_id}")
        return True
    
    def checkout_branch(self, branch_name: str, create: bool = False) -> bool:
        """Simulate checking out a branch."""
        self.current_branch = branch_name
        logger.info(f"Switched to fake branch: {branch_name}")
        return True
    
    def commit(self, commit_message: str) -> bool:
        """Simulate committing changes."""
        logger.info(f"Fake commit with message: {commit_message}")
        
        # Store the current state of files for this commit
        commit_files = {}
        
        for root, _, files in os.walk(self.temp_dir):
            if any(part.startswith('.') for part in root.split(os.sep)):
                continue
                
            for file in files:
                _, ext = os.path.splitext(file)
                if ext.lower() not in self.code_file_extensions:
                    continue
                    
                temp_path = os.path.join(root, file)
                rel_path = os.path.relpath(temp_path, self.temp_dir)
                
                try:
                    with open(temp_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        # Update original files for revert_changes()
                        self.original_files[rel_path] = content
                        # Store in this commit
                        commit_files[rel_path] = content
                except Exception as e:
                    logger.error(f"Error updating original file content for {rel_path}: {e}")
        
        # Store this commit by name
        self.commits[commit_message] = commit_files
        
        return True
    
    def handle_post_execution(self, config: dict, commit_message: str) -> bool:
        """Simulate post-execution handling."""
        return self.commit(commit_message)
    
    def get_github_web_url(self) -> str:
        """Return a placeholder GitHub URL."""
        return "https://github.com/fake/repository"
    
    def ensure_gitignore_includes_tac(self):
        """No-op for fake git manager."""
        pass
    
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
    
    @classmethod
    def for_performance_testing(cls, repo_path: str = '.') -> 'FakeGitManager':
        """
        Create a FakeGitManager instance configured for performance testing.
        
        This class method creates a temporary directory and initializes a FakeGitManager
        that copies all code files from the original repository to the temporary directory.
        
        Args:
            repo_path: Path to the original repository
            
        Returns:
            FakeGitManager: A FakeGitManager instance initialized with a temporary directory
        """
        temp_dir = tempfile.mkdtemp(prefix="tac_performance_")
        logger.info(f"Created temporary directory for performance testing: {temp_dir}")
        
        return cls(repo_path=repo_path, temp_dir=temp_dir) 