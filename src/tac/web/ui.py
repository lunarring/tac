import asyncio
import json
import websockets
import socket
import os
import signal
import subprocess
import argparse
import traceback
import difflib
from tac.agents.misc.chat import ChatAgent
from tac.utils.project_files import ProjectFiles
from tac.utils.audio import Speech2Text  # Newly imported for speech-to-text functionality
from tac.blocks.processor import BlockProcessor
from tac.cli.main import execute_command
from tac.core.llm import LLMClient, Message
from tac.core.config import config, ConfigManager
from tac.utils.git_manager import create_git_manager

class UIManager:
    def __init__(self, base_dir="."):
        self.base_dir = base_dir
        self.project_files = ProjectFiles(self.base_dir)
        self.speech_to_text = Speech2Text()
        self.is_recording = False
        self.task_instructions = None
        self.websocket = None
        self._loop = None
        self._status_queue = asyncio.Queue()
        self.max_attempts = 4  # Maximum attempts
        # Add lock for thread safety
        self._status_lock = asyncio.Lock()
        # Git manager for diffs
        self.git_manager = create_git_manager()
        # Config is already initialized when imported
        # Pre-check git status at initialization
        self.git_clean = None
        self.git_status_message = None
        
        # Perform early git check during initialization
        if self.git_manager and config.git.enabled:
            try:
                self.git_clean = self.git_manager.is_clean()
                if not self.git_clean:
                    self.git_status_message = "⚠️ Git workspace is not clean. Please commit or stash your changes before proceeding."
            except Exception as e:
                self.git_clean = False
                self.git_status_message = f"⚠️ Git error: {str(e)}"
        else:
            self.git_clean = True
            if not config.git.enabled:
                self.git_status_message = "Git operations are disabled in config."

    def send_status_bar(self, message):
        """
        Safe method to update the status bar from any context (sync or async).
        Can be called from both the main thread and background threads.
        """
        print(f"Status update requested: {message}")
        if self._loop and self._loop.is_running():
            try:
                # If we're in an async context with a running loop
                future = asyncio.run_coroutine_threadsafe(self._status_queue.put(message), self._loop)
                # Don't wait for the result to avoid blocking
                print(f"Status message queued: {message}")
            except Exception as e:
                print(f"Error queueing status message: {e}")
                # Fallback - try to send directly if queueing fails
                if self.websocket:
                    try:
                        asyncio.run_coroutine_threadsafe(self.send_status_message(message), self._loop)
                    except Exception as e2:
                        print(f"Fallback status send failed: {e2}")
        elif self.websocket:
            # If we don't have a loop yet, try to get one and send directly
            try:
                loop = self._get_loop()
                asyncio.run_coroutine_threadsafe(self.send_status_message(message), loop)
                print(f"Status message sent via new loop: {message}")
            except Exception as e:
                print(f"Failed to send status via new loop: {e}")

    async def _process_status_queue(self):
        """Process status messages from the queue"""
        while True:
            try:
                message = await self._status_queue.get()
                # Use lock to prevent multiple concurrent status updates
                async with self._status_lock:
                    await self.send_status_message(message)
                self._status_queue.task_done()
            except Exception as e:
                print(f"Error processing status queue: {e}")
                # Don't break the loop on error
                await asyncio.sleep(0.1)

    def _get_loop(self):
        if self._loop is None:
            try:
                self._loop = asyncio.get_event_loop()
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
        return self._loop

    async def send_status_message(self, message):
        """Direct async method to send status messages with awaiting"""
        if self.websocket:
            try:
                # Check if this is an attempt update message from the processor
                processor_attempt_match = None
                if "Starting block creation and execution attempt" in message:
                    # Extract the attempt info from the processor log message
                    processor_attempt_match = message.split("Starting block creation and execution attempt ")[1].split(" of ")
                    if len(processor_attempt_match) == 2:
                        current = processor_attempt_match[0]
                        max_attempts = processor_attempt_match[1]
                        # Update message to match the format in the processor
                        message = f"Starting attempt {current} of {max_attempts}..."
                
                await self.websocket.send(json.dumps({
                    "type": "status_message",
                    "message": message
                }))
                print(f"Status update sent: {message}")  # Log sent messages
            except Exception as e:
                print(f"Error sending status message: {e}")

    async def send_protoblock_data(self, protoblock):
        """
        Send protoblock data to the client to display in the UI.
        
        Args:
            protoblock: The ProtoBlock object containing all the details
        """
        if self.websocket and protoblock:
            # Get attempt number from processor's idx_attempt in run_loop
            # Format attempt number using max_attempts from config
            attempt_number = f"{protoblock.attempt_number}/{self.max_attempts}"
            
            # Convert protoblock to a suitable JSON format for display
            protoblock_data = {
                "type": "protoblock_data",
                "attempt": attempt_number,
                "block_id": protoblock.block_id,
                "task_description": protoblock.task_description,
                "context_files": protoblock.context_files,
                "write_files": protoblock.write_files,
                "trusty_agents": protoblock.trusty_agents,
                "trusty_agent_prompts": protoblock.trusty_agent_prompts or {}
            }
            
            print(f"Sending protoblock data to client: {json.dumps(protoblock_data, indent=2)}")
            await self.websocket.send(json.dumps(protoblock_data))
            print("Protoblock data sent successfully")

    async def load_high_level_summaries(self):
        data = self.project_files.get_all_summaries()
        formatted_strings = []
        for rel_path, file_info in data.get("files", {}).items():
            if "error" in file_info:
                summary = f"Error analyzing file: {file_info['error']}"
            else:
                summary = file_info.get("summary_high_level", "No summary available")
            formatted_strings.append(f"###FILE: {rel_path}\n{summary}\n###END_FILE")
        return "\n\n".join(formatted_strings)

    async def check_git_status(self):
        """Check git status early to prevent issues later. Returns True if git is clean or not enabled."""
        # Use cached result if available
        if self.git_clean is not None:
            if self.git_status_message:
                await self.send_status_message(self.git_status_message)
            return self.git_clean
            
        # If not cached, perform the check
        if not config.git.enabled:
            self.git_status_message = "Git operations are disabled in config."
            await self.send_status_message(self.git_status_message)
            self.git_clean = True
            return True
            
        await self.send_status_message("Checking git status...")
        git_manager = create_git_manager()
        
        if not git_manager.is_clean():
            self.git_status_message = "❌ Git workspace is not clean. Please commit or stash your changes before proceeding."
            await self.send_status_message(self.git_status_message)
            
            # Check if auto-stash is enabled - get the value manually since safe_get doesn't accept a default parameter
            auto_stash = False
            try:
                # Check if the general section has auto_stash attribute
                if hasattr(config.general, 'auto_stash'):
                    auto_stash = config.general.auto_stash
                # If not found, try to get it from config.safe_get without a default
                else:
                    auto_stash_value = config.safe_get('general', 'auto_stash')
                    if auto_stash_value is not None:
                        auto_stash = auto_stash_value
            except:
                # If any error occurs, default to False
                auto_stash = False
                
            if auto_stash:
                await self.send_status_message("Auto-stash is enabled. Stashing changes...")
                if git_manager.revert_changes():
                    await self.send_status_message("✅ Changes successfully stashed.")
                    self.git_clean = True
                    self.git_status_message = "✅ Git workspace is clean (auto-stashed)."
                    return True
                else:
                    await self.send_status_message("❌ Failed to stash changes. Please clean your git workspace manually.")
                    self.git_clean = False
                    return False
            else:
                await self.send_status_message("Please commit or stash your changes before proceeding.")
                self.git_clean = False
                return False
        
        self.git_status_message = "✅ Git workspace is clean."
        await self.send_status_message(self.git_status_message)
        self.git_clean = True
        return True

    async def dummy_mic_click(self, websocket):
        if not self.is_recording:
            self.speech_to_text.start_recording()
            print("Recording started.")
            self.is_recording = True
        else:
            transcript = self.speech_to_text.stop_recording()
            print("Recording stopped. Transcript:", transcript)
            self.is_recording = False
            if transcript:
                payload = {
                    "type": "transcribed_message",
                    "message": transcript
                }
                await self.websocket.send(json.dumps(payload))

    def count_diff_lines(self, diff_text):
        """Count added and removed lines in a diff.
        
        Args:
            diff_text: The diff text to analyze
            
        Returns:
            tuple: (added_lines, removed_lines)
        """
        if not diff_text or not isinstance(diff_text, str):
            return 0, 0
            
        added = 0
        removed = 0
        
        # Count lines that start with + or - but not ++ or --
        for line in diff_text.splitlines():
            if line.startswith('+') and not line.startswith('+++'):
                added += 1
            elif line.startswith('-') and not line.startswith('---'):
                removed += 1
                
        return added, removed

    async def handle_file_diff_request(self, filename):
        """
        Handles a request for a diff of a specific file.
        Gets the diff for the file from git and sends it back to the client.
        
        Args:
            filename: The name of the file to get the diff for
        """
        try:
            # Standardize the filename to reduce path issues
            filename = filename.strip()
            
            await self.send_status_message(f"Getting diff for {filename}...")
            
            # Check if the file exists
            filepath = os.path.join(self.base_dir, filename)
            if not os.path.exists(filepath):
                await self.send_error_response(filename, f"File {filename} does not exist")
                return
            
            # Always read the current file content for comparison
            try:
                with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                    current_content = f.read()
            except Exception as read_err:
                await self.send_error_response(filename, f"Could not read file: {str(read_err)}")
                return
                
            # In UI mode, we disabled auto_commit, so changes should be in working directory
            if not self.git_manager or not hasattr(self.git_manager, 'repo') or not self.git_manager.repo:
                # No git, just return the file content
                await self.websocket.send(json.dumps({
                    "type": "file_diff_response",
                    "filename": filename,
                    "diff": f"Full file content (no git):\n{current_content}"
                }))
                return
                
            # Get diff info from git
            try:
                # Is this a tracked file?
                is_tracked = False
                try:
                    tracked_files = self.git_manager.repo.git.ls_files().split('\n')
                    is_tracked = filename in tracked_files
                except Exception:
                    pass
                    
                # Is this an untracked file?
                is_untracked = filename in self.git_manager.repo.untracked_files
                
                # First check for unstaged changes (most common in UI mode)
                unstaged_diff = ""
                try:
                    unstaged_diff = self.git_manager.repo.git.diff('--', filename)
                except Exception:
                    pass
                    
                # Then check for staged changes
                staged_diff = ""
                try:
                    staged_diff = self.git_manager.repo.git.diff('--staged', '--', filename)
                except Exception:
                    pass
                
                # Format appropriate diff output
                if unstaged_diff:
                    # Found unstaged changes - show those
                    diff = unstaged_diff
                elif staged_diff:
                    # Found staged changes - show those
                    diff = staged_diff
                elif is_untracked:
                    # Untracked new file - show all content as added
                    diff = f"diff --git a/{filename} b/{filename}\n--- /dev/null\n+++ b/{filename}\n"
                    diff += "".join([f"+{line}\n" for line in current_content.splitlines()])
                elif is_tracked:
                    # File is tracked but no git changes detected - might be unchanged
                    # In UI mode, this is uncommon because we disabled auto-commit
                    # Try to get original content to compare manually
                    try:
                        original_content = self.git_manager.repo.git.show(f"HEAD:{filename}")
                        if original_content != current_content:
                            # Manual diff - file changed but git didn't detect it
                            diff_lines = difflib.unified_diff(
                                original_content.splitlines(),
                                current_content.splitlines(),
                                fromfile=f'a/{filename}',
                                tofile=f'b/{filename}',
                                lineterm=''
                            )
                            diff = '\n'.join(diff_lines)
                        else:
                            diff = f"File is tracked but hasn't changed."
                    except Exception as e:
                        # Cannot get original version, just show current
                        diff = f"Current file content (couldn't get original):\n{current_content}"
                else:
                    # Not tracked, not untracked - should not happen
                    diff = f"File status unknown. Current content:\n{current_content}"
                    
            except Exception as git_err:
                print(f"Git error getting diff: {git_err}")
                traceback.print_exc()
                # Fall back to showing current content
                diff = f"Current file content (git error: {str(git_err)}):\n{current_content}"
            
            # Send the result
            await self.websocket.send(json.dumps({
                "type": "file_diff_response",
                "filename": filename,
                "diff": diff
            }))
            
        except Exception as e:
            await self.send_error_response(filename, f"Unexpected error: {str(e)}")
            traceback.print_exc()

    async def send_error_response(self, filename, error_message):
        """Helper method to send error responses for file diff requests"""
        if self.websocket:
            try:
                await self.websocket.send(json.dumps({
                    "type": "file_diff_response",
                    "filename": filename,
                    "error": error_message
                }))
            except Exception as e:
                print(f"Error sending error response: {e}")

    async def handle_file_status_request(self, filename):
        """
        Handles a request to check if a file has been modified.
        Checks the git status of the file and returns whether it has been modified.
        
        Args:
            filename: The name of the file to check
        """
        try:
            # Standardize the filename to reduce path issues
            filename = filename.strip()
            
            # Check if the file exists
            filepath = os.path.join(self.base_dir, filename)
            if not os.path.exists(filepath):
                await self.websocket.send(json.dumps({
                    "type": "file_status_response",
                    "filename": filename,
                    "is_modified": False,
                    "error": "File does not exist"
                }))
                return
            
            is_modified = False
            added_lines = 0
            removed_lines = 0
            diff_text = ""
            
            # Check if file is modified using git
            if self.git_manager and hasattr(self.git_manager, 'repo') and self.git_manager.repo:
                try:
                    # Is this a tracked file?
                    is_tracked = False
                    try:
                        tracked_files = self.git_manager.repo.git.ls_files().split('\n')
                        is_tracked = filename in tracked_files
                    except Exception:
                        pass
                        
                    # Is this an untracked file?
                    is_untracked = filename in self.git_manager.repo.untracked_files
                    
                    # Check for unstaged changes
                    unstaged_diff = ""
                    try:
                        unstaged_diff = self.git_manager.repo.git.diff('--', filename)
                    except Exception:
                        pass
                        
                    # Check for staged changes
                    staged_diff = ""
                    try:
                        staged_diff = self.git_manager.repo.git.diff('--staged', '--', filename)
                    except Exception:
                        pass
                    
                    # Determine if the file is modified and get diff for line counting
                    if unstaged_diff:
                        # Has unstaged diff changes
                        is_modified = True
                        diff_text = unstaged_diff
                    elif staged_diff:
                        # Has staged diff changes
                        is_modified = True
                        diff_text = staged_diff
                    elif is_untracked:
                        # New file - all lines are added
                        is_modified = True
                        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                            content = f.read()
                        added_lines = len(content.splitlines())
                        removed_lines = 0
                    elif is_tracked:
                        # Tracked but no git diff - check content manually
                        try:
                            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                                current_content = f.read()
                            original_content = self.git_manager.repo.git.show(f"HEAD:{filename}")
                            is_modified = original_content != current_content
                            
                            if is_modified:
                                # Generate diff for line counting
                                diff_lines = difflib.unified_diff(
                                    original_content.splitlines(),
                                    current_content.splitlines(),
                                    fromfile=f'a/{filename}',
                                    tofile=f'b/{filename}',
                                    lineterm=''
                                )
                                diff_text = '\n'.join(diff_lines)
                        except Exception:
                            # Can't determine, assume unmodified
                            is_modified = False
                    else:
                        # Unknown status
                        is_modified = False
                    
                    # Count lines if we have a diff
                    if diff_text:
                        added_lines, removed_lines = self.count_diff_lines(diff_text)
                        
                except Exception as git_err:
                    # Error checking git status, assume unmodified
                    print(f"Error checking git status: {git_err}")
                    is_modified = False
            else:
                # No git, all files are considered modified in UI mode
                is_modified = True
                # Can't count lines without git, so just return is_modified
            
            # Send the response with line counts
            await self.websocket.send(json.dumps({
                "type": "file_status_response",
                "filename": filename,
                "is_modified": is_modified,
                "added_lines": added_lines,
                "removed_lines": removed_lines
            }))
            
        except Exception as e:
            print(f"Error handling file status request: {e}")
            traceback.print_exc()
            await self.websocket.send(json.dumps({
                "type": "file_status_response",
                "filename": filename,
                "is_modified": False,
                "error": str(e)
            }))
            
    async def handle_connection(self, websocket):
        self.websocket = websocket
        self._loop = asyncio.get_running_loop()
        
        # Start the status queue processor right away and save it as instance variable
        self._status_processor = asyncio.create_task(self._process_status_queue())
        
        # Send initial status
        await self.send_status_message("Connected. Initializing...")
        
        # Display pre-checked git status as a prominent message if there are issues
        if self.git_status_message and not self.git_clean:
            # Send as an error_message for more visibility in the UI
            await self.websocket.send(json.dumps({
                "type": "error_message",
                "message": self.git_status_message
            }))
            await self.send_status_message("Warning: Git status check failed. You can chat but execution may be limited.")
        
        # Check git status again (will use cached result from init if available)
        git_clean = await self.check_git_status()
        if not git_clean:
            # Still allow chat, but user will be notified of git issues
            await self.send_status_message("Warning: Git status check failed. You can chat but execution may be limited.")
        
        # Load file summaries
        await self.send_status_message("Loading project file summaries...")
        file_summaries = await self.load_high_level_summaries()
        
        await self.send_status_message("Ready. Waiting for instructions...")

        system_content = (
            "A high level summary of the codebase which the user wants to modify is here: {file_summaries}. Always reply concise and without formatting. Your task is to ask questions and clarify requests, for this early phase of software design. Always try to be brief and concise and help the planning. Remember, the user is not the one who is implementing the code, it is actually you and your team of AI agents and they use trusty agents to verify the code. So don't tell the user how to do it themselves, but rather try to gather information about what the user wants to build in the context of the codebase above. Don't be too verbose about the code itself, but rather gather an understanding of what the user really wants. Always be brief and to the point! However the goal is to end up with ONE clear task and do them one at a time. Ideally just answer in ONE sentence and not more! Also if you feel we have enough information, tell the user that they should hit the block button below to start the protoblock execution.")
        formatted_system_content = system_content.format(file_summaries=file_summaries)
        chat_agent = ChatAgent(system_prompt=formatted_system_content)

        try:
            while True:
                try:
                    user_input_raw = await websocket.recv()
                    print("Received message from client:", user_input_raw)
                    user_message = None

                    try:
                        data = json.loads(user_input_raw)
                        if isinstance(data, dict) and "type" in data:
                            message_type = data["type"]
                            if message_type == "mic_click":
                                await self.dummy_mic_click(websocket)
                                continue
                            elif message_type == "block_click":
                                await self.handle_block_click(websocket, chat_agent)
                                continue
                            elif message_type == "file_diff_request":
                                await self.handle_file_diff_request(data.get("filename", ""))
                                continue
                            elif message_type == "file_status_request":
                                await self.handle_file_status_request(data.get("filename", ""))
                                continue
                            elif message_type == "git_branch_request":
                                await self.handle_git_branch_request()
                                continue
                            elif message_type == "git_commit_request":
                                await self.handle_git_commit_request(data.get("commit_message", ""))
                                continue
                            elif message_type == "git_discard_request":
                                await self.handle_git_discard_request()
                                continue
                            elif message_type == "git_merge_request":
                                await self.handle_git_merge_request(data.get("target_branch", ""))
                                continue
                            elif message_type in ["user_message", "transcribed_message"]:
                                user_message = data.get("message", "").strip()
                        else:
                            user_message = user_input_raw.strip()
                    except json.JSONDecodeError:
                        if user_input_raw.strip() == "mic_click":
                            await self.dummy_mic_click(websocket)
                            continue
                        user_message = user_input_raw.strip()

                    if user_message:
                        assistant_reply = chat_agent.process_message(user_message)
                        print(f"Sending message to client: {assistant_reply}")
                        await websocket.send(assistant_reply)
                except websockets.exceptions.ConnectionClosed:
                    break
                except Exception as e:
                    print(f"Error in processing message: {e}")
                    break
        finally:
            # Cancel the status processor when connection is closed
            if hasattr(self, '_status_processor'):
                self._status_processor.cancel()
                try:
                    await self._status_processor
                except asyncio.CancelledError:
                    pass
            # Clear websocket reference
            self.websocket = None

    async def handle_block_click(self, websocket, chat_agent):
        try:
            # Send status immediately
            await self.send_status_message("Creating block from conversation...")
            genesis_prompt = chat_agent.generate_task_instructions()

            # Check git status again before proceeding
            git_clean = await self.check_git_status()
            if not git_clean:
                await self.send_status_message("❌ Cannot proceed with block execution due to git status issues.")
                await self.websocket.send(json.dumps({
                    "type": "error_message",
                    "message": "Git workspace is not clean. Please commit or stash your changes before proceeding."
                }))
                return

            # Load codebase information
            await self.send_status_message("Analyzing codebase...")
            project_files = ProjectFiles()
            codebase = project_files.get_codebase_summary()

            # Disable auto commit in UI mode to allow viewing diffs
            config_overrides = {
                'no_git': False,
                'json': None,
                'image': None,
                'git': {
                    'auto_commit_if_success': False  # Disable auto commit to allow diff viewing
                }
            }
            for attr in ['llm_type', 'model', 'api_base', 'json_mode']:
                config_overrides[attr] = None

            # Send status update before creating processor
            await self.send_status_message("Initializing task processor...")

            # Use BlockProcessor directly
            from tac.blocks.processor import BlockProcessor
            
            # Create a processor instance with all required parameters
            processor = BlockProcessor(
                task_instructions=genesis_prompt,
                codebase=codebase,
                config_override=config_overrides,
                ui_manager=self
            )
            
            # Send status update right before generating protoblock
            await self.send_status_message("Analyzing task requirements...")
            
            # Get the protoblock before execution for immediate display
            try:
                # Create the protoblock
                processor.create_protoblock(idx_attempt=0, error_analysis="")
                
                if processor.protoblock:
                    # Display protoblock as soon as it's created, before execution
                    await self.send_status_message("Generated protoblock. Preparing execution...")
                    await self.send_protoblock_data(processor.protoblock)
                    # Small delay to ensure UI updates
                    await asyncio.sleep(0.5)
            except Exception as e:
                print(f"Error creating protoblock: {e}")
                traceback.print_exc()
                await self.send_status_message(f"❌ Error creating protoblock: {str(e)[:100]}...")
                # Ensure we remove any previous protoblock display
                await self.websocket.send(json.dumps({
                    "type": "remove_protoblock",
                    "message": "Failed to create protoblock"
                }))
                return
            
            # Execute the processor directly
            await self.send_status_message("Starting block execution and agent processing...")
            
            # For the first attempt, make sure we use the same format as in processor.py
            await self.send_status_message("Starting block creation and execution attempt 1 of 4")
            
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(None, processor.run_loop)

            # Check if execution was successful and we have a protoblock
            if success and processor.protoblock:
                await self.send_status_message("✅ Block executed successfully! Displaying final results...")
                # Send updated protoblock data after execution with the final attempt number
                await self.send_protoblock_data(processor.protoblock)
                
                # Inform user that changes are uncommitted and can be viewed
                await self.websocket.send(json.dumps({
                    "type": "info_message",
                    "message": "Changes have been made but not committed. Click on any file in the 'Files to Modify' section to view the changes."
                }))
            else:
                # If block execution failed, send explicit failure message
                await self.send_status_message("❌ Block execution failed!")
                # Force removal of protoblock display
                await self.websocket.send(json.dumps({
                    "type": "remove_protoblock",
                    "message": "Block execution failed"
                }))

        except Exception as e:
            print(f"Error during block execution: {e}")
            traceback.print_exc()
            await self.send_status_message(f"❌ Error: {str(e)}")
            # Force removal of protoblock display on any exception
            await self.websocket.send(json.dumps({
                "type": "remove_protoblock",
                "message": f"Error: {str(e)[:100]}"
            }))

    async def handle_git_branch_request(self):
        """Handle request to get all available git branches"""
        if not self.websocket:
            return
            
        await self.send_status_message("Fetching git branches...")
        
        branches = []
        
        try:
            if self.git_manager and self.git_manager.repo:
                # Get all branches
                for branch in self.git_manager.repo.branches:
                    branches.append(branch.name)
                    
                # Sort branches alphabetically
                branches.sort()
                
                await self.websocket.send(json.dumps({
                    "type": "git_branch_response",
                    "branches": branches
                }))
                await self.send_status_message("Ready")
            else:
                await self.websocket.send(json.dumps({
                    "type": "git_branch_response",
                    "branches": [],
                    "error": "Git repository not available"
                }))
                await self.send_status_message("Git repository not available")
        except Exception as e:
            print(f"Error getting git branches: {e}")
            traceback.print_exc()
            await self.websocket.send(json.dumps({
                "type": "git_branch_response",
                "branches": [],
                "error": str(e)
            }))
            await self.send_status_message(f"Error: {str(e)}")
            
    async def handle_git_commit_request(self, commit_message):
        """Handle request to commit changes"""
        if not self.websocket:
            return
            
        # Validate commit message
        if not commit_message:
            commit_message = "Changes from TAC block execution"
        
        await self.send_status_message("Committing changes...")
        
        try:
            if self.git_manager and self.git_manager.repo:
                # Use the commit method from GitManager
                success = self.git_manager.commit(commit_message)
                
                if success:
                    response_message = "Changes committed successfully"
                    await self.websocket.send(json.dumps({
                        "type": "git_operation_response",
                        "operation": "commit",
                        "success": True,
                        "message": response_message
                    }))
                    await self.send_status_message(f"✅ {response_message}")
                else:
                    await self.websocket.send(json.dumps({
                        "type": "git_operation_response",
                        "operation": "commit",
                        "success": False,
                        "message": "Failed to commit changes"
                    }))
                    await self.send_status_message("❌ Failed to commit changes")
            else:
                await self.websocket.send(json.dumps({
                    "type": "git_operation_response",
                    "operation": "commit",
                    "success": False,
                    "message": "Git repository not available"
                }))
                await self.send_status_message("❌ Git repository not available")
        except Exception as e:
            print(f"Error committing changes: {e}")
            traceback.print_exc()
            await self.websocket.send(json.dumps({
                "type": "git_operation_response",
                "operation": "commit",
                "success": False,
                "message": f"Error: {str(e)}"
            }))
            await self.send_status_message(f"❌ Error committing changes: {str(e)}")
    
    async def handle_git_discard_request(self):
        """Handle request to discard changes"""
        if not self.websocket:
            return
            
        await self.send_status_message("Discarding changes...")
        
        try:
            if self.git_manager and self.git_manager.repo:
                # Use the revert_changes method from GitManager
                success = self.git_manager.revert_changes()
                
                if success:
                    response_message = "Changes discarded successfully"
                    await self.websocket.send(json.dumps({
                        "type": "git_operation_response",
                        "operation": "discard",
                        "success": True,
                        "message": response_message
                    }))
                    await self.send_status_message(f"✅ {response_message}")
                else:
                    await self.websocket.send(json.dumps({
                        "type": "git_operation_response",
                        "operation": "discard",
                        "success": False,
                        "message": "Failed to discard changes"
                    }))
                    await self.send_status_message("❌ Failed to discard changes")
            else:
                await self.websocket.send(json.dumps({
                    "type": "git_operation_response",
                    "operation": "discard",
                    "success": False,
                    "message": "Git repository not available"
                }))
                await self.send_status_message("❌ Git repository not available")
        except Exception as e:
            print(f"Error discarding changes: {e}")
            traceback.print_exc()
            await self.websocket.send(json.dumps({
                "type": "git_operation_response",
                "operation": "discard",
                "success": False,
                "message": f"Error: {str(e)}"
            }))
            await self.send_status_message(f"❌ Error discarding changes: {str(e)}")
    
    async def handle_git_merge_request(self, target_branch):
        """Handle request to merge changes to a branch and delete current branch"""
        if not self.websocket:
            return
            
        # Validate target branch
        if not target_branch:
            await self.websocket.send(json.dumps({
                "type": "git_operation_response",
                "operation": "merge",
                "success": False,
                "message": "No target branch specified"
            }))
            await self.send_status_message("❌ No target branch specified")
            return
            
        await self.send_status_message(f"Merging to {target_branch}...")
        
        try:
            if self.git_manager and self.git_manager.repo:
                # Get current branch
                current_branch = self.git_manager.get_current_branch()
                
                if not current_branch:
                    await self.websocket.send(json.dumps({
                        "type": "git_operation_response",
                        "operation": "merge",
                        "success": False,
                        "message": "Could not determine current branch"
                    }))
                    await self.send_status_message("❌ Could not determine current branch")
                    return
                
                # First commit any pending changes
                if not self.git_manager.is_clean():
                    commit_success = self.git_manager.commit(f"Changes before merging to {target_branch}")
                    if not commit_success:
                        await self.websocket.send(json.dumps({
                            "type": "git_operation_response",
                            "operation": "merge",
                            "success": False,
                            "message": "Failed to commit pending changes before merge"
                        }))
                        await self.send_status_message("❌ Failed to commit pending changes before merge")
                        return
                
                # Now perform the merge operation
                try:
                    # Switch to target branch
                    self.git_manager.repo.git.checkout(target_branch)
                    
                    # Merge the current branch
                    self.git_manager.repo.git.merge(current_branch)
                    
                    # Delete the current branch if not on the same branch
                    if current_branch != target_branch:
                        self.git_manager.repo.git.branch('-D', current_branch)
                    
                    response_message = f"Merged to {target_branch} and deleted {current_branch}"
                    await self.websocket.send(json.dumps({
                        "type": "git_operation_response",
                        "operation": "merge",
                        "success": True,
                        "message": response_message
                    }))
                    await self.send_status_message(f"✅ {response_message}")
                except git.GitCommandError as e:
                    # Try to abort any failed merge
                    try:
                        self.git_manager.repo.git.merge('--abort')
                    except:
                        pass
                        
                    # Try to go back to original branch
                    try:
                        self.git_manager.repo.git.checkout(current_branch)
                    except:
                        pass
                        
                    await self.websocket.send(json.dumps({
                        "type": "git_operation_response",
                        "operation": "merge",
                        "success": False,
                        "message": f"Merge failed: {str(e)}"
                    }))
                    await self.send_status_message(f"❌ Merge failed: {str(e)}")
            else:
                await self.websocket.send(json.dumps({
                    "type": "git_operation_response",
                    "operation": "merge",
                    "success": False,
                    "message": "Git repository not available"
                }))
                await self.send_status_message("❌ Git repository not available")
        except Exception as e:
            print(f"Error merging branches: {e}")
            traceback.print_exc()
            await self.websocket.send(json.dumps({
                "type": "git_operation_response",
                "operation": "merge",
                "success": False,
                "message": f"Error: {str(e)}"
            }))
            await self.send_status_message(f"❌ Error merging branches: {str(e)}")

    async def run_server(self):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('localhost', 8765))
                s.close()
        except OSError:
            try:
                result = subprocess.run(['pgrep', '-f', 'python.*tac'], capture_output=True, text=True)
                if result.stdout.strip():
                    pids = result.stdout.strip().split('\n')
                    for pid_str in pids:
                        try:
                            pid = int(pid_str)
                            print(f"Killing existing Python process (PID: {pid}) using port 8765")
                            os.kill(pid, signal.SIGTERM)
                        except Exception as e:
                            print(f"Failed to kill process {pid_str}: {e}")
                    await asyncio.sleep(1)
                else:
                    print("Port 8765 is in use but no Python TAC processes found. Please free the port manually.")
                    raise OSError("Port 8765 is in use by non-Python process")
            except Exception as e:
                print(f"Failed to kill existing processes: {e}")

        server = await websockets.serve(self.handle_connection, 'localhost', 8765)
        print("WebSocket server started on ws://localhost:8765")
        print("Please open 'src/tac/web/index.html' in your browser to view the UI.")
        try:
            await asyncio.Future()  # Run forever
        except asyncio.CancelledError:
            server.close()
            await server.wait_closed()
            raise

    def launch_ui(self):
        try:
            # Check git status before starting the server to catch issues early
            if hasattr(self, 'git_manager') and self.git_manager:
                if not config.git.enabled:
                    print("Git operations are disabled in config.")
                else:
                    print("Checking git status...")
                    if not self.git_manager.is_clean():
                        print("⚠️ Git workspace is not clean. You may encounter issues during block execution.")
                        print("Consider committing or stashing your changes before proceeding.")
                        
                        # Check if auto-stash is enabled
                        auto_stash = False
                        try:
                            if hasattr(config.general, 'auto_stash'):
                                auto_stash = config.general.auto_stash
                            else:
                                auto_stash_value = config.safe_get('general', 'auto_stash')
                                if auto_stash_value is not None:
                                    auto_stash = auto_stash_value
                        except:
                            pass
                            
                        if auto_stash:
                            print("Auto-stash is enabled. Stashing changes...")
                            if self.git_manager.revert_changes():
                                print("✅ Changes successfully stashed.")
                            else:
                                print("❌ Failed to stash changes. Please clean your git workspace manually.")
                    else:
                        print("✅ Git workspace is clean.")
            
            asyncio.run(self.run_server())
        except KeyboardInterrupt:
            print("WebSocket server stopped by user.")