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
import git
from tac.agents.misc.chat import ChatAgent
from tac.utils.project_files import ProjectFiles
from tac.utils.audio import Speech2Text
from tac.blocks.processor import BlockProcessor
from tac.cli.main import execute_command
from tac.core.llm import LLMClient, Message
from tac.core.config import config, ConfigManager
from tac.utils.git_manager import create_git_manager
from tac.agents.trusty.pytest import PytestTestingAgent
from tac.web.websocket_server import WebSocketServer  # Import the new WebSocketServer
from tac.web.ui_components import (
    ChatPanel, 
    ProtoBlockView, 
    FileDiffView, 
    GitView, 
    SpeechInput
)
from tac.blocks.generator import ProtoBlockGenerator  # Add this import
import time


class MessageHandlerManager:
    """
    Centralized manager for handling UI messages from both component system and legacy system.
    Eliminates duplicate handling code by providing a single implementation for each message type.
    """
    def __init__(self, ui_manager):
        self.ui = ui_manager
        
    async def handle_user_message(self, data, websocket=None):
        """Handle a user message"""
        message = data.get("message", "").strip()
        if not message:
            return
            
        print(f"Received user message: {message[:50]}{'...' if len(message) > 50 else ''}")
        
        # Use the persistent ChatAgent from the UIManager
        if self.ui.chat_agent is None:
            # Initialize ChatAgent if it doesn't exist yet (should be rare since it's initialized with file summaries)
            system_content = self.ui.CHAT_SYSTEM_PROMPT.format(file_summaries=self.ui.file_summaries or "No file summaries available yet")
            self.ui.chat_agent = ChatAgent(system_prompt=system_content)
            
        # Process the message using the persistent ChatAgent
        assistant_reply = self.ui.chat_agent.process_message(message)
        
        # Send the response back to the client
        if websocket:
            # Legacy mode: send directly to websocket
            await websocket.send(assistant_reply)
        elif self.ui.websocket:
            # Component mode: use the stored websocket reference
            await self.ui.websocket.send(assistant_reply)
    
    async def handle_transcribed_message(self, data, websocket=None):
        """Handle a transcribed message from speech input"""
        transcription = data.get("message", "").strip()
        if not transcription:
            return
            
        # First send the transcription to the chat panel as a user message
        await self.ui.chat_panel.send_message({
            "type": "chat_message",
            "role": "user",
            "message": transcription
        })
        
        # Process the message using the chat agent
        if self.ui.chat_agent is None:
            system_content = self.ui.CHAT_SYSTEM_PROMPT.format(file_summaries=self.ui.file_summaries or "No file summaries available yet")
            self.ui.chat_agent = ChatAgent(system_prompt=system_content)
            
        # Process the message using the persistent ChatAgent
        assistant_reply = self.ui.chat_agent.process_message(transcription)
        
        # Send the assistant's response to the chat panel
        await self.ui.chat_panel.send_message({
            "type": "chat_message",
            "role": "assistant",
            "message": assistant_reply
        })
    
    async def handle_mic_click(self, data=None, websocket=None):
        """
        Handle a microphone click by implementing the logic directly.
        This method is called whenever the microphone button is clicked.
        """
        try:
            # Import necessary modules
            import os
            import tempfile
            import subprocess
            import time
            
            # Extract the client's desired recording state
            client_recording = True  # Default
            if data and isinstance(data, dict) and 'recording' in data:
                client_recording = bool(data.get('recording'))
            
            # Debounce logic to prevent multiple rapid clicks of the same type
            current_time = time.time()
            last_click_time = getattr(self, '_last_mic_click_time', 0)
            last_click_state = getattr(self, '_last_click_state', None)
            
            # Save current click info for next time
            self._last_mic_click_time = current_time
            self._last_click_state = client_recording
            
            # Only debounce if this is a repeat click with the same state
            if (current_time - last_click_time < self.ui.CLICK_DEBOUNCE_TIME and 
                last_click_state == client_recording):
                print(f"Ignoring duplicate mic click - too soon ({current_time - last_click_time:.2f}s)")
                return
            
            # Handle the click based on our current state and client's desired state
            if not self.ui.is_recording and client_recording:
                # START RECORDING
                print("Starting recording...")
                await self.ui.send_status_message("Recording audio...")
                
                # If the recorder is in a bad state, recreate it
                if hasattr(self.ui.speech_to_text, 'audio_recorder') and self.ui.speech_to_text.audio_recorder is not None:
                    # Try to clean up the existing recorder
                    try:
                        if hasattr(self.ui.speech_to_text.audio_recorder, 'cleanup'):
                            self.ui.speech_to_text.audio_recorder.cleanup()
                    except Exception:
                        pass
                    
                    # Replace with a fresh recorder if recording previously failed
                    if getattr(self.ui.speech_to_text.audio_recorder, 'is_recording', False):
                        from tac.utils.audio import AudioRecorder
                        self.ui.speech_to_text.audio_recorder = AudioRecorder()
                
                # Check if we can access PyAudio
                import pyaudio
                p = pyaudio.PyAudio()
                device_count = p.get_device_count()
                print(f"Pre-recording check: {device_count} audio devices available")
                p.terminate()
                
                # Update UI state BEFORE starting the recording
                self.ui.is_recording = True
                await self.ui.speech_input.send_recording_status(True)
                
                # Start the speech recording
                self.ui.speech_to_text.start_recording()
                
            elif self.ui.is_recording and not client_recording:
                # STOP RECORDING
                print("Stopping recording...")
                
                # Update UI state BEFORE stopping the recording
                self.ui.is_recording = False
                await self.ui.speech_input.send_recording_status(False)
                
                # Direct approach - the modified stop_recording method now handles everything
                try:
                    result = self.ui.speech_to_text.stop_recording()
                    
                    if result:
                        print(f"Speech transcription: {result}")
                        
                        # Send transcription to chat as a user message
                        await self.handle_transcribed_message({"message": result}, websocket)
                    else:
                        print("No transcription result, recording may have been too short")
                        await self.ui.send_status_message("No transcription result, recording may have been too short")
                        
                except Exception as inner_err:
                    print(f"Error during stop_recording: {inner_err}")
                    import traceback
                    traceback.print_exc()
                    
                    # Try to clean up any files or resources
                    try:
                        if hasattr(self.ui.speech_to_text, 'audio_recorder'):
                            self.ui.speech_to_text.audio_recorder.cleanup()
                    except Exception:
                        pass
                    
                    raise  # Re-raise to handle in outer exception handler
            else:
                print(f"Ignoring mic click - state already matches ({self.ui.is_recording}={client_recording})")
        except Exception as e:
            print(f"Error in microphone handling: {e}")
            traceback.print_exc()
            self.ui.is_recording = False
            await self.ui.speech_input.send_recording_status(False)
            await self.ui.send_status_message(f"Microphone error: {str(e)}")
            
    async def handle_transcribed_text(self, transcription, websocket=None):
        """
        Handle transcribed text as a user message.
        
        Args:
            transcription: The transcribed text from speech recognition
            websocket: Optional websocket connection
        """
        if not transcription:
            return
            
        # Create a user message with the transcription
        user_message = {"type": "user_message", "message": transcription}
        
        # Process the message
        await self.handle_user_message(user_message, websocket)
        
        # Update the status bar
        await self.ui.send_status_message(f"Transcription: {transcription}")
    
    async def handle_block_click(self, data=None, websocket=None):
        """Handle a block click"""
        # Use the persistent ChatAgent instead of creating a new one each time
        if self.ui.chat_agent is None:
            # This shouldn't happen normally, but handle it just in case
            system_content = self.ui.CHAT_SYSTEM_PROMPT.format(file_summaries=self.ui.file_summaries or "No file summaries available yet")
            self.ui.chat_agent = ChatAgent(system_prompt=system_content)
            
        await self.ui.handle_block_click(websocket, self.ui.chat_agent)
    
    async def handle_file_diff_request(self, data, websocket=None):
        """Handle a file diff request"""
        filename = data.get("filename", "")
        await self.ui.handle_file_diff_request(filename)
    
    async def handle_file_status_request(self, data, websocket=None):
        """Handle a file status request"""
        filename = data.get("filename", "")
        await self.ui.handle_file_status_request(filename)
    
    async def handle_git_branch_request(self, data=None, websocket=None):
        """Handle a git branch request"""
        await self.ui.handle_git_branch_request()
    
    async def handle_git_commit_request(self, data, websocket=None):
        """Handle a git commit request"""
        commit_message = data.get("commit_message", "")
        await self.ui.handle_git_commit_request(commit_message)
    
    async def handle_git_discard_request(self, data=None, websocket=None):
        """Handle a git discard request"""
        await self.ui.handle_git_discard_request()
    
    async def handle_git_merge_request(self, data, websocket=None):
        """Handle a git merge request"""
        target_branch = data.get("target_branch", "")
        await self.ui.handle_git_merge_request(target_branch)


class UIManager:
    # System prompt template for ChatAgent
    CHAT_SYSTEM_PROMPT = (
        "A high level summary of the codebase which the user wants to modify is here: {file_summaries}. "
        "Always reply concise and without formatting. Your task is to ask questions and clarify requests, "
        "for this early phase of software design. Always try to be brief and concise and help the planning. "
        "Remember, the user is not the one who is implementing the code, it is actually you and your team of "
        "AI agents and they use trusty agents to verify the code. So don't tell the user how to do it themselves, "
        "but rather try to gather information about what the user wants to build in the context of the codebase above. "
        "Don't be too verbose about the code itself, but rather gather an understanding of what the user really wants. "
        "Always be brief and to the point! However the goal is to end up with ONE clear task and do them one at a time. "
        "Ideally just answer in ONE sentence and not more! Also if you feel we have enough information, tell the user that "
        "they should hit the block button below to start the protoblock execution."
    )
    
    # Add a new class variable to track the last mic click time
    CLICK_DEBOUNCE_TIME = 1.0  # Seconds to ignore additional clicks
    
    def __init__(self, base_dir="."):
        self.base_dir = base_dir
        self.project_files = ProjectFiles(self.base_dir)
        
        # Check audio devices availability before creating Speech2Text
        self._test_audio_devices()
        
        # Use the real Speech2Text implementation
        self.speech_to_text = Speech2Text()
        
        # Debug: Check if speech_to_text initialized properly
        import inspect
        print(f"Speech2Text instance: {self.speech_to_text}")
        print(f"Speech2Text methods: {[m for m in dir(self.speech_to_text) if not m.startswith('_')]}")
        
        self.is_recording = False
        self.task_instructions = None
        self.file_summaries = None
        self.chat_agent = None  # Will be initialized when file_summaries are loaded
        
        # Create a websocket server instance
        self.server = WebSocketServer(host='localhost', port=8765)
        
        # Create UI components
        self.chat_panel = ChatPanel()
        self.protoblock_view = ProtoBlockView(max_attempts=4)
        self.file_diff_view = FileDiffView()
        self.git_view = GitView()
        self.speech_input = SpeechInput()
        
        # Create the message handler manager
        self.message_handler = MessageHandlerManager(self)
        
        # Register all components with the server
        self.server.register_component(self.chat_panel)
        self.server.register_component(self.protoblock_view)
        self.server.register_component(self.file_diff_view)
        self.server.register_component(self.git_view)
        self.server.register_component(self.speech_input)
        
        # Register message types with components
        self.server.register_message_type("user_message", self.chat_panel)
        self.server.register_message_type("transcribed_message", self.chat_panel)
        self.server.register_message_type("file_diff_request", self.file_diff_view)
        self.server.register_message_type("file_status_request", self.file_diff_view)
        self.server.register_message_type("git_branch_request", self.git_view)
        self.server.register_message_type("git_commit_request", self.git_view)
        self.server.register_message_type("git_discard_request", self.git_view)
        self.server.register_message_type("git_merge_request", self.git_view)
        self.server.register_message_type("mic_click", self.speech_input)
        
        # Keep websocket and loop references for backward compatibility
        self.websocket = None
        self._loop = None
        self._status_lock = asyncio.Lock()
        self.max_attempts = 4  # Maximum attempts
        
        # Git manager for diffs
        self.git_manager = create_git_manager()
        
        # Pre-check git status at initialization
        self.git_clean = None
        self.git_status_message = None
        
        # Background task trackers
        self._background_tasks = {}
        self._test_runner = PytestTestingAgent()
        
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
                
        # Register message handlers with the WebSocketServer
        self._register_message_handlers()

    def _test_audio_devices(self):
        """Test if audio devices are accessible in the current context"""
        try:
            import pyaudio
            p = pyaudio.PyAudio()
            
            # Get device count
            device_count = p.get_device_count()
            print(f"Audio devices found: {device_count}")
            
            # Print device info
            for i in range(device_count):
                device_info = p.get_device_info_by_index(i)
                print(f"Device {i}: {device_info['name']}")
                print(f"  Input channels: {device_info['maxInputChannels']}")
                print(f"  Output channels: {device_info['maxOutputChannels']}")
                print(f"  Default sample rate: {device_info['defaultSampleRate']}")
            
            # Get default input device
            try:
                default_input = p.get_default_input_device_info()
                print(f"Default input device: {default_input['name']} (index {default_input['index']})")
            except IOError:
                print("No default input device available")
            
            # Clean up
            p.terminate()
            print("Audio device test completed successfully")
            
        except Exception as e:
            print(f"Error testing audio devices: {e}")
            import traceback
            traceback.print_exc()
            print("Audio functionality may not work properly")

    async def create_or_restart_background_task(self, task_name, task_coroutine):
        """
        Create a new background task or restart it if it's done.
        
        Args:
            task_name: Name of the task for tracking
            task_coroutine: The coroutine to run as a background task
            
        Returns:
            The created or existing task
        """
        if task_name not in self._background_tasks or self._background_tasks[task_name].done():
            self._background_tasks[task_name] = asyncio.create_task(task_coroutine())
            print(f"Started background task: {task_name}")
        return self._background_tasks[task_name]

    async def start_background_tasks(self):
        """Start essential background tasks when the UI starts"""
        # Start file indexing task
        await self.create_or_restart_background_task('file_indexer', self._background_file_indexer)
        
        # If test running is enabled in config, start the test runner
        if config.safe_get('general', 'run_tests_in_background', False):
            await self.create_or_restart_background_task('test_runner', self._background_test_runner)

    async def _background_file_indexer(self):
        """Background task to index files periodically"""
        try:
            await self.send_status_message("Starting background file indexing...")
            while True:
                try:
                    # Perform file indexing
                    self.project_files.refresh_index()
                    
                    # Update file summaries
                    self.file_summaries = await self.load_high_level_summaries()
                    
                    # Delay before next indexing
                    await asyncio.sleep(60)  # Index every minute
                except asyncio.CancelledError:
                    # Allow task to be cancelled
                    raise
                except Exception as e:
                    print(f"Error in background file indexer: {e}")
                    await asyncio.sleep(5)  # Shorter delay after error
        except asyncio.CancelledError:
            print("Background file indexer cancelled")
            raise

    async def _background_test_runner(self):
        """Background task to run tests periodically"""
        try:
            self.last_run_time = asyncio.get_event_loop().time()
            await self.send_status_message("Starting background test runner...")
            
            while True:
                try:
                    # Wait time between test runs (10 minutes by default)
                    wait_time = config.safe_get('general', 'background_test_interval', 600)
                    
                    # Get current time
                    current_time = asyncio.get_event_loop().time()
                    
                    # Check if enough time has passed since last run
                    if (current_time - self.last_run_time) < wait_time:
                        # Not enough time has passed, wait some more
                        await asyncio.sleep(30)  # Check again in 30 seconds
                        continue
                    
                    # Check git status before running tests
                    git_clean = await self.check_git_status()
                    if not git_clean:
                        # Git workspace not clean, skip tests
                        await self.send_status_message("Background tests skipped: Git workspace not clean")
                        await asyncio.sleep(wait_time)  # Wait before checking again
                        continue
                    
                    # Update last run time
                    self.last_run_time = current_time
                    
                    # Run tests in background
                    test_path = config.safe_get('general', 'test_path', 'tests')
                    await self.send_status_message(f"Running background tests from {test_path}...")
                    
                    # Run tests in executor to prevent blocking
                    loop = asyncio.get_event_loop()
                    
                    # Properly handle test results
                    try:
                        test_result = await loop.run_in_executor(
                            None, 
                            lambda: self._test_runner.run_tests(test_path)
                        )
                        
                        # Get test statistics
                        test_stats = self._test_runner.get_test_stats()
                        total = sum(test_stats.values())
                        
                        # Log test results with detailed statistics
                        if test_result:
                            await self.send_status_message(
                                f"✅ Background tests: {test_stats['passed']}/{total} passed"
                            )
                        else:
                            # Detailed failure reporting
                            failed_msg = f"❌ Background tests: {test_stats['failed']} failed"
                            if test_stats.get('error', 0) > 0:
                                failed_msg += f", {test_stats['error']} errors"
                            await self.send_status_message(failed_msg)
                            
                            # Send more detailed message to chat panel
                            await self.chat_panel.send_error_message(
                                f"Background tests detected issues: {test_stats['failed']} tests failed" +
                                (f", {test_stats['error']} errors" if test_stats.get('error', 0) > 0 else "") +
                                ". Check the console for details."
                            )
                    except Exception as test_err:
                        print(f"Error running tests: {test_err}")
                        await self.send_status_message(f"❌ Error running background tests: {str(test_err)}")
                        await self.chat_panel.send_error_message(f"Error running background tests: {str(test_err)}")
                    
                    # Wait before next test run
                    await asyncio.sleep(wait_time)
                    
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    print(f"Error in background test runner: {e}")
                    await asyncio.sleep(60)  # Wait a minute before trying again
                    
        except asyncio.CancelledError:
            print("Background test runner cancelled")
            raise

    def send_status_bar(self, message):
        """
        Safe method to update the status bar from any context (sync or async).
        Can be called from both the main thread and background threads.
        """
        # Delegate to the WebSocketServer
        self.server.send_status_bar(message)

    async def send_status_message(self, message):
        """Direct async method to send status messages with awaiting"""
        # Delegate to the WebSocketServer with error handling
        try:
            await self.server.send_status_message(message)
        except Exception as e:
            print(f"Error sending status message: {e}")
            # If there's an error with the server method, try direct websocket send as fallback
            if self.websocket:
                try:
                    status_data = {"type": "status_message", "message": message}
                    await self.websocket.send(json.dumps(status_data))
                    print(f"Status message sent directly: {message}")
                except Exception as direct_err:
                    print(f"Error sending status message directly: {direct_err}")
            else:
                print(f"Status message not sent (no websocket): {message}")

    async def send_protoblock_data(self, protoblock):
        """
        Send protoblock data to the client to display in the UI.
        
        Args:
            protoblock: The ProtoBlock object containing all the details
        """
        # Delegate to the ProtoBlockView component
        await self.protoblock_view.send_protoblock_data(protoblock)

    async def load_high_level_summaries(self):
        """
        Load high-level summaries of all files in the project.
        
        Returns:
            str: Formatted summary text for all files
        """
        try:
            # Get all summaries from the project files
            data = self.project_files.get_all_summaries()
            formatted_strings = []
            
            # Get total file count for logging
            total_files = len(data.get("files", {}))
            error_count = 0
            
            # Process each file
            for rel_path, file_info in data.get("files", {}).items():
                if "error" in file_info:
                    summary = f"Error analyzing file: {file_info['error']}"
                    error_count += 1
                else:
                    summary = file_info.get("summary_high_level", "No summary available")
                    
                    # Format the summary with file path
                    formatted_strings.append(f"###FILE: {rel_path}\n{summary}\n###END_FILE")
            
            # Log summary statistics
            if error_count > 0:
                await self.send_status_message(
                    f"Loaded {total_files} file summaries with {error_count} errors"
                )
                
            summaries = "\n\n".join(formatted_strings)
            
            # Initialize or update the chat agent with the new summaries
            if self.chat_agent is None:
                system_content = self.CHAT_SYSTEM_PROMPT.format(file_summaries=summaries)
                self.chat_agent = ChatAgent(system_prompt=system_content)
            
            return summaries
            
        except Exception as e:
            await self.handle_error(e, "load_high_level_summaries", notify_user=False)
            # Return a minimal summary as fallback
            return "Error loading file summaries. Please check the console for details."

    async def check_git_status(self):
        """
        Check the git status of the workspace.
        
        Returns:
            bool: True if git workspace is clean, False otherwise
        """
        try:
            # Always report success if git is disabled in config
            if not config.git.enabled:
                self.git_clean = True
                self.git_status_message = "Git operations are disabled in config."
                return True
                
            # Skip check if git_manager is not available
            if not self.git_manager:
                self.git_clean = True
                self.git_status_message = "Git manager not available."
                return True
            
            # Perform actual git check
            self.git_clean = self.git_manager.is_clean()
            if not self.git_clean:
                self.git_status_message = "⚠️ Git workspace is not clean. Please commit or stash your changes before proceeding."
                
                # Check if auto-stash is enabled
                auto_stash = config.safe_get('general', 'auto_stash', False)
                
                if auto_stash:
                    await self.send_status_message("Auto-stash is enabled. Stashing changes...")
                    if self.git_manager.revert_changes():
                        self.git_clean = True
                        self.git_status_message = "✅ Changes successfully stashed."
                        await self.send_status_message("✅ Changes successfully stashed.")
                    return True
                else:
                    self.git_status_message = "❌ Failed to stash changes. Please clean your git workspace manually."
                    await self.send_status_message("❌ Failed to stash changes.")
            else:
                self.git_status_message = "✅ Git workspace is clean."
                
            return self.git_clean
            
        except Exception as e:
            print(f"Error checking git status: {e}")
            traceback.print_exc()
            self.git_clean = False
            self.git_status_message = f"⚠️ Git error: {str(e)}"
            await self.send_status_message(f"⚠️ Git error: {str(e)}")
            return False
        
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
                await self.file_diff_view.send_error(filename, f"File {filename} does not exist")
                return
            
            # Always read the current file content for comparison
            try:
                with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                    current_content = f.read()
            except Exception as read_err:
                await self.file_diff_view.send_error(filename, f"Could not read file: {str(read_err)}")
                await self.handle_error(read_err, "handle_file_diff_request", "FileDiffView", False)
                return
                
            # In UI mode, we disabled auto_commit, so changes should be in working directory
            if not self.git_manager or not hasattr(self.git_manager, 'repo') or not self.git_manager.repo:
                # No git, just return the file content
                await self.file_diff_view.send_file_diff(
                    filename,
                    f"Full file content (no git):\n{current_content}"
                )
                return
                
            # Get diff info from git
            try:
                # Is this a tracked file?
                is_tracked = False
                try:
                    tracked_files = self.git_manager.repo.git.ls_files().split('\n')
                    is_tracked = filename in tracked_files
                except Exception as track_err:
                    await self.handle_error(track_err, "handle_file_diff_request (track check)", "FileDiffView", False)
                    
                # Is this an untracked file?
                is_untracked = filename in self.git_manager.repo.untracked_files
                
                # First check for unstaged changes (most common in UI mode)
                unstaged_diff = ""
                try:
                    unstaged_diff = self.git_manager.repo.git.diff('--', filename)
                except Exception as unstaged_err:
                    await self.handle_error(unstaged_err, "handle_file_diff_request (unstaged diff)", "FileDiffView", False)
                    
                # Then check for staged changes
                staged_diff = ""
                try:
                    staged_diff = self.git_manager.repo.git.diff('--staged', '--', filename)
                except Exception as staged_err:
                    await self.handle_error(staged_err, "handle_file_diff_request (staged diff)", "FileDiffView", False)
                
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
                await self.handle_error(git_err, "handle_file_diff_request (git diff)", "FileDiffView", False)
                # Fall back to showing current content
                diff = f"Current file content (git error: {str(git_err)}):\n{current_content}"
            
            # Send the result
            await self.file_diff_view.send_file_diff(filename, diff)
            
        except Exception as e:
            await self.handle_error(e, "handle_file_diff_request", "FileDiffView")
            await self.file_diff_view.send_error(filename, f"Unexpected error: {str(e)}")

    async def send_error_response(self, filename, error_message):
        """Helper method to send error responses for file diff requests"""
        try:
            await self.file_diff_view.send_error(filename, error_message)
        except Exception as e:
            await self.handle_error(e, "send_error_response", "FileDiffView", False)

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
                await self.file_diff_view.send_file_status(
                    filename=filename,
                    is_modified=False,
                    error="File does not exist"
                )
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
            await self.file_diff_view.send_file_status(
                filename=filename,
                is_modified=is_modified,
                added_lines=added_lines,
                removed_lines=removed_lines
            )
            
        except Exception as e:
            print(f"Error handling file status request: {e}")
            traceback.print_exc()
            await self.file_diff_view.send_file_status(
                filename=filename,
                is_modified=False,
                error=str(e)
            )

    async def _on_websocket_connect(self, websocket):
        """Handle a new WebSocket connection"""
        # Keep references for backwards compatibility
        self.websocket = websocket
        self._loop = asyncio.get_running_loop()
        
        # Send initial status
        await self.send_status_message("Connected. Initializing...")
        
        # Start background tasks
        await self.start_background_tasks()
        
        # Display pre-checked git status as a prominent message if there are issues
        if self.git_status_message and not self.git_clean:
            # Send as an error_message for more visibility in the UI
            await self.chat_panel.send_error_message(self.git_status_message)
            await self.send_status_message("Warning: Git status check failed. You can chat but execution may be limited.")
        
        # Check git status again (will use cached result from init if available)
        git_clean = await self.check_git_status()
        if not git_clean:
            # Still allow chat, but user will be notified of git issues
            await self.send_status_message("Warning: Git status check failed. You can chat but execution may be limited.")
        
        # Load file summaries
        await self.send_status_message("Loading project file summaries...")
        self.file_summaries = await self.load_high_level_summaries()
        
        # Ensure we have a ChatAgent instance properly initialized
        if self.chat_agent is None:
            system_content = self.CHAT_SYSTEM_PROMPT.format(file_summaries=self.file_summaries)
            self.chat_agent = ChatAgent(system_prompt=system_content)
            await self.send_status_message("Chat agent initialized with codebase summaries")
        
        await self.send_status_message("Ready. Waiting for instructions...")

    async def _on_websocket_disconnect(self, websocket):
        """Handle WebSocket disconnection"""
        print(f"WebSocket connection closed")
        
        # If this is our current websocket, remove the reference
        if self.websocket == websocket:
            self.websocket = None
            
        # No need to clean up everything on disconnect - the client might reconnect
        # Just mark that we're no longer connected
        await self.send_status_message("Client disconnected")

    def _register_message_handlers(self):
        """Register message handlers with the WebSocketServer and UI components"""
        # Register component message handlers - use the centralized handler implementation
        self.chat_panel.register_message_handler("user_message", 
            lambda data: asyncio.create_task(self.message_handler.handle_user_message(data)))
        
        self.chat_panel.register_message_handler("transcribed_message", 
            lambda data: asyncio.create_task(self.message_handler.handle_transcribed_message(data)))
        
        self.file_diff_view.register_message_handler("file_diff_request", 
            lambda data: asyncio.create_task(self.message_handler.handle_file_diff_request(data)))
        
        self.file_diff_view.register_message_handler("file_status_request", 
            lambda data: asyncio.create_task(self.message_handler.handle_file_status_request(data)))
        
        self.git_view.register_message_handler("git_branch_request", 
            lambda data: asyncio.create_task(self.message_handler.handle_git_branch_request(data)))
        
        self.git_view.register_message_handler("git_commit_request", 
            lambda data: asyncio.create_task(self.message_handler.handle_git_commit_request(data)))
        
        self.git_view.register_message_handler("git_discard_request", 
            lambda data: asyncio.create_task(self.message_handler.handle_git_discard_request(data)))
        
        self.git_view.register_message_handler("git_merge_request", 
            lambda data: asyncio.create_task(self.message_handler.handle_git_merge_request(data)))
        
        self.speech_input.register_message_handler("mic_click", 
            lambda data: asyncio.create_task(self.message_handler.handle_mic_click(data)))
        
        # Also register legacy message handlers using the same implementation
        self.server.register_message_handler("mic_click", 
            lambda ws, data: asyncio.create_task(self.message_handler.handle_mic_click(data, ws)))
        
        self.server.register_message_handler("block_click", 
            lambda ws, data: asyncio.create_task(self.message_handler.handle_block_click(data, ws)))
        
        self.server.register_message_handler("file_diff_request", 
            lambda ws, data: asyncio.create_task(self.message_handler.handle_file_diff_request(data, ws)))
        
        self.server.register_message_handler("file_status_request", 
            lambda ws, data: asyncio.create_task(self.message_handler.handle_file_status_request(data, ws)))
        
        self.server.register_message_handler("git_branch_request", 
            lambda ws, data: asyncio.create_task(self.message_handler.handle_git_branch_request(data, ws)))
        
        self.server.register_message_handler("git_commit_request", 
            lambda ws, data: asyncio.create_task(self.message_handler.handle_git_commit_request(data, ws)))
        
        self.server.register_message_handler("git_discard_request", 
            lambda ws, data: asyncio.create_task(self.message_handler.handle_git_discard_request(data, ws)))
        
        self.server.register_message_handler("git_merge_request", 
            lambda ws, data: asyncio.create_task(self.message_handler.handle_git_merge_request(data, ws)))
        
        self.server.register_message_handler("transcribed_message", 
            lambda ws, data: asyncio.create_task(self.message_handler.handle_transcribed_message(data, ws)))
        
        # Register connection handlers
        self.server.register_connection_handler(self._on_websocket_connect)
        self.server.register_disconnection_handler(self._on_websocket_disconnect)
    
    async def notify_tests_run(self):
        """
        Notify the background test runner that tests were recently executed.
        This prevents duplicate test runs in a short time period.
        """
        if 'test_runner' in self._background_tasks and not self._background_tasks['test_runner'].done():
            previous_time = getattr(self, 'last_run_time', 0)
            self.last_run_time = asyncio.get_event_loop().time()
            
            # Calculate when next run would occur
            wait_time = config.safe_get('general', 'background_test_interval', 600)
            next_run = self.last_run_time + wait_time
            
            # Format as readable time
            from datetime import datetime, timedelta
            next_time = datetime.now() + timedelta(seconds=wait_time)
            next_formatted = next_time.strftime("%H:%M:%S")
            
            await self.send_status_message(
                f"Background test runner notified of manual test run. Next run at {next_formatted}"
            )
            return True
        return False

    async def handle_block_click(self, websocket, chat_agent):
        try:
            # Send status immediately
            await self.send_status_message("Creating block from conversation...")
            
            try:
                # Get conversation history from chat agent
                conversation = chat_agent.get_messages()
                # Format the conversation for the prompt
                conversation_text = "\n".join([f"{msg.role}: {msg.content}" for msg in conversation])
                
                # Send status about extracting task from conversation
                await self.send_status_message("Converting conversation to task instructions...")
                
                # Create a protoblock generator and get the genesis prompt
                protoblock_generator = ProtoBlockGenerator(ui_manager=self)
                task_instructions = f"Based on the following conversation between a user and an AI assistant, determine what task the user wants to implement:\n\n{conversation_text}\n\nFocus on the most recent request from the user and create clear, actionable instructions."
                
                # Note: The codebase parameter is required but immediately replaced within the method
                genesis_prompt = protoblock_generator.get_protoblock_genesis_prompt(codebase="", task_instructions=task_instructions)
                
                if not genesis_prompt:
                    await self.send_status_message("❌ Failed to generate protoblock prompt.")
                    await self.chat_panel.send_error_message(
                        "Failed to generate protoblock prompt. Please provide more detailed information about what you want to accomplish."
                    )
                    return
            except Exception as prompt_err:
                await self.send_status_message(f"❌ Error generating protoblock prompt: {str(prompt_err)}")
                await self.chat_panel.send_error_message(
                    f"Error generating protoblock prompt: {str(prompt_err)}. Please try again with more specific instructions."
                )
                return

            # Check git status before proceeding
            git_clean = await self.check_git_status()
            if not git_clean:
                await self.send_status_message("❌ Cannot proceed with block execution due to git status issues.")
                await self.chat_panel.send_error_message(
                    "Git workspace is not clean. Please commit or stash your changes before proceeding."
                )
                return

            # Load codebase information
            await self.send_status_message("Analyzing codebase...")
            try:
                project_files = ProjectFiles()
                codebase = project_files.get_codebase_summary()
            except Exception as codebase_err:
                await self.send_status_message(f"❌ Error analyzing codebase: {str(codebase_err)}")
                await self.chat_panel.send_error_message(
                    f"Error analyzing codebase: {str(codebase_err)}. Please check that your project structure is valid."
                )
                return

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

            # If tests are running in the background, set run_tests_first to False to avoid duplication
            run_tests_first = config.safe_get('general', 'run_tests_first', True)
            if config.safe_get('general', 'run_tests_in_background', False) and 'test_runner' in self._background_tasks and not self._background_tasks['test_runner'].done():
                config_overrides['general'] = {
                    'run_tests_first': False
                }
            
            # Send status update before creating processor
            await self.send_status_message("Initializing task processor...")

            # Use BlockProcessor directly
            from tac.blocks.processor import BlockProcessor
            
            # Create a processor instance with all required parameters
            try:
                processor = BlockProcessor(
                    task_instructions=genesis_prompt,
                    codebase=codebase,
                    config_override=config_overrides,
                    ui_manager=self
                )
            except Exception as processor_err:
                await self.send_status_message(f"❌ Error initializing processor: {str(processor_err)}")
                await self.chat_panel.send_error_message(
                    f"Error initializing task processor: {str(processor_err)}. Please try again."
                )
                return
            
            # Send status update right before generating protoblock
            await self.send_status_message("Analyzing task requirements...")
            
            # Get the protoblock before execution for immediate display
            try:
                # Create the protoblock
                processor.create_protoblock(idx_attempt=0, error_analysis="")
                
                if not processor.protoblock:
                    await self.send_status_message("❌ Failed to create protoblock.")
                    await self.chat_panel.send_error_message(
                        "Failed to create a protoblock from your instructions. Please provide more specific details about what you want to accomplish."
                    )
                    return
                    
                # Display protoblock as soon as it's created, before execution
                await self.send_status_message("Generated protoblock. Preparing execution...")
                await self.protoblock_view.send_protoblock_data(processor.protoblock)
                # Small delay to ensure UI updates
                await asyncio.sleep(0.5)
            except Exception as e:
                print(f"Error creating protoblock: {e}")
                traceback.print_exc()
                await self.send_status_message(f"❌ Error creating protoblock: {str(e)[:100]}...")
                # Ensure we remove any previous protoblock display
                await self.protoblock_view.remove_protoblock("Failed to create protoblock")
                return
            
            # Execute the processor directly
            await self.send_status_message("Starting block execution and agent processing...")
            
            # For the first attempt, make sure we use the same format as in processor.py
            await self.send_status_message("Starting block creation and execution attempt 1 of 4")
            
            # Create a cancellable task for the block execution instead of using an executor
            # This ensures we can interrupt execution with CTRL+C
            block_task = None
            
            try:
                # Define a coroutine that wraps the processor.run_loop() method
                async def run_processor():
                    loop = asyncio.get_event_loop()
                    return await loop.run_in_executor(None, processor.run_loop)
                
                # Create and store the task
                block_task = asyncio.create_task(run_processor())
                self._background_tasks['current_block'] = block_task
                
                # Wait for the task to complete
                success = await block_task
                
                # If tests were run during block execution and background tests are enabled,
                # notify the background test runner
                if run_tests_first and config.safe_get('general', 'run_tests_in_background', False):
                    await self.notify_tests_run()

                # Check if execution was successful and we have a protoblock
                if success and processor.protoblock:
                    await self.send_status_message("✅ Block executed successfully! Displaying final results...")
                    # Send updated protoblock data after execution with the final attempt number
                    await self.protoblock_view.send_protoblock_data(processor.protoblock)
                    
                    # Inform user that changes are uncommitted and can be viewed
                    await self.chat_panel.send_info_message(
                        "Changes have been made but not committed. Click on any file in the 'Files to Modify' section to view the changes."
                    )
                else:
                    # If block execution failed, send explicit failure message
                    await self.send_status_message("❌ Block execution failed!")
                    # Force removal of protoblock display
                    await self.protoblock_view.remove_protoblock("Block execution failed")
                    
            except asyncio.CancelledError:
                # Task was cancelled (e.g., by CTRL+C)
                await self.send_status_message("❌ Block execution cancelled by user.")
                await self.protoblock_view.remove_protoblock("Execution cancelled by user")
                # Re-raise the exception to propagate the cancellation
                raise
                
            except Exception as exec_err:
                print(f"Error during block execution: {exec_err}")
                traceback.print_exc()
                await self.send_status_message(f"❌ Block execution failed: {str(exec_err)}")
                await self.protoblock_view.remove_protoblock(f"Execution error: {str(exec_err)[:100]}")
                
            finally:
                # Clean up the task reference
                if 'current_block' in self._background_tasks:
                    del self._background_tasks['current_block']

        except asyncio.CancelledError:
            # Propagate cancellation
            print("Block execution cancelled by user (CTRL+C)")
            await self.send_status_message("Block execution cancelled by user (CTRL+C)")
            raise
            
        except Exception as e:
            print(f"Error during block execution: {e}")
            traceback.print_exc()
            await self.send_status_message(f"❌ Error: {str(e)}")
            # Force removal of protoblock display on any exception
            await self.protoblock_view.remove_protoblock(f"Error: {str(e)[:100]}")

    async def handle_git_branch_request(self):
        """Handle request to get all available git branches"""
        await self.send_status_message("Fetching git branches...")
        
        branches = []
        
        try:
            if self.git_manager and self.git_manager.repo:
                # Get all branches
                for branch in self.git_manager.repo.branches:
                    branches.append(branch.name)
                    
                # Sort branches alphabetically
                branches.sort()
                
                await self.git_view.send_branches(branches)
                await self.send_status_message("Ready")
            else:
                await self.git_view.send_branches([], error="Git repository not available")
                await self.send_status_message("Git repository not available")
        except Exception as e:
            print(f"Error getting git branches: {e}")
            traceback.print_exc()
            await self.git_view.send_branches([], error=str(e))
            await self.send_status_message(f"Error: {str(e)}")
            
    async def handle_git_commit_request(self, commit_message):
        """Handle request to commit changes"""
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
                    await self.git_view.send_operation_result(
                        operation="commit",
                        success=True,
                        message=response_message
                    )
                    await self.send_status_message(f"✅ {response_message}")
                else:
                    await self.git_view.send_operation_result(
                        operation="commit",
                        success=False,
                        message="Failed to commit changes"
                    )
                    await self.send_status_message("❌ Failed to commit changes")
            else:
                await self.git_view.send_operation_result(
                    operation="commit",
                    success=False,
                    message="Git repository not available"
                )
                await self.send_status_message("❌ Git repository not available")
        except Exception as e:
            print(f"Error committing changes: {e}")
            traceback.print_exc()
            await self.git_view.send_operation_result(
                operation="commit",
                success=False,
                message=f"Error: {str(e)}"
            )
            await self.send_status_message(f"❌ Error committing changes: {str(e)}")
    
    async def handle_git_discard_request(self):
        """Handle request to discard changes"""
        await self.send_status_message("Discarding changes...")
        
        try:
            if self.git_manager and self.git_manager.repo:
                # Use the revert_changes method from GitManager
                success = self.git_manager.revert_changes()
                
                if success:
                    response_message = "Changes discarded successfully"
                    await self.git_view.send_operation_result(
                        operation="discard",
                        success=True,
                        message=response_message
                    )
                    await self.send_status_message(f"✅ {response_message}")
                else:
                    await self.git_view.send_operation_result(
                        operation="discard",
                        success=False,
                        message="Failed to discard changes"
                    )
                    await self.send_status_message("❌ Failed to discard changes")
            else:
                await self.git_view.send_operation_result(
                    operation="discard",
                    success=False,
                    message="Git repository not available"
                )
                await self.send_status_message("❌ Git repository not available")
        except Exception as e:
            print(f"Error discarding changes: {e}")
            traceback.print_exc()
            await self.git_view.send_operation_result(
                operation="discard",
                success=False,
                message=f"Error: {str(e)}"
            )
            await self.send_status_message(f"❌ Error discarding changes: {str(e)}")
    
    async def handle_git_merge_request(self, target_branch):
        """Handle request to merge changes to a branch and delete current branch"""
        # Validate target branch
        if not target_branch:
            await self.git_view.send_operation_result(
                operation="merge",
                success=False,
                message="No target branch specified"
            )
            await self.send_status_message("❌ No target branch specified")
            return
            
        await self.send_status_message(f"Merging to {target_branch}...")
        
        try:
            if self.git_manager and self.git_manager.repo:
                # Get current branch
                current_branch = self.git_manager.get_current_branch()
                
                if not current_branch:
                    await self.git_view.send_operation_result(
                        operation="merge",
                        success=False,
                        message="Could not determine current branch"
                    )
                    await self.send_status_message("❌ Could not determine current branch")
                    return
                
                # First commit any pending changes
                if not self.git_manager.is_clean():
                    commit_success = self.git_manager.commit(f"Changes before merging to {target_branch}")
                    if not commit_success:
                        await self.git_view.send_operation_result(
                            operation="merge",
                            success=False,
                            message="Failed to commit pending changes before merge"
                        )
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
                    await self.git_view.send_operation_result(
                        operation="merge",
                        success=True,
                        message=response_message
                    )
                    await self.send_status_message(f"✅ {response_message}")
                except Exception as e:
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
                        
                    await self.git_view.send_operation_result(
                        operation="merge",
                        success=False,
                        message=f"Merge failed: {str(e)}"
                    )
                    await self.send_status_message(f"❌ Merge failed: {str(e)}")
            else:
                await self.git_view.send_operation_result(
                    operation="merge",
                    success=False,
                    message="Git repository not available"
                )
                await self.send_status_message("❌ Git repository not available")
        except Exception as e:
            print(f"Error merging branches: {e}")
            traceback.print_exc()
            await self.git_view.send_operation_result(
                operation="merge",
                success=False,
                message=f"Error: {str(e)}"
            )
            await self.send_status_message(f"❌ Error merging branches: {str(e)}")

    def launch_ui(self):
        """
        Launch the WebSocket UI server with proper startup sequence and error handling.
        """
        loop = asyncio.get_event_loop()
        
        # Set up signal handlers for graceful shutdown
        try:
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(
                    sig,
                    lambda s=sig: asyncio.create_task(self._handle_exit_signal(s))
                )
            print("Signal handlers registered for graceful shutdown (CTRL+C)")
        except NotImplementedError:
            # Windows doesn't support SIGINT/SIGTERM signal handlers
            print("Warning: Signal handlers not supported on this platform")
            pass
            
        try:
            print("\n=== TAC Web UI Startup ===")
            print(f"Base directory: {self.base_dir}")
            
            # Check for potential issues before starting
            self._pre_launch_checks()
            
            # Launch the server
            print("\nStarting WebSocket server at ws://localhost:8765")
            print("Press Ctrl+C to stop the server")
            self.server.launch()
            
        except KeyboardInterrupt:
            print("\nWebSocket server stopped by user")
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self.shutdown())
                else:
                    asyncio.run(self.shutdown())
            except Exception as shutdown_err:
                print(f"Error during shutdown: {shutdown_err}")
                
        except Exception as e:
            print(f"\nError starting WebSocket server: {e}")
            traceback.print_exc()
            print("\nServer failed to start. Please check the error message above.")
            try:
                asyncio.run(self.shutdown())
            except Exception as shutdown_err:
                print(f"Error during shutdown: {shutdown_err}")
                
    async def _handle_exit_signal(self, signal):
        """Handle exit signal gracefully"""
        print(f"\nReceived exit signal {signal.name}, shutting down...")
        
        # Force cancel any running block execution
        if 'current_block' in self._background_tasks and not self._background_tasks['current_block'].done():
            print("Forcefully cancelling running block execution...")
            self._background_tasks['current_block'].cancel()
            try:
                # Give it a short timeout to clean up
                await asyncio.wait_for(self._background_tasks['current_block'], timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                # Expected when cancelling
                pass
                
        await self.shutdown()
        
        # Stop the event loop
        loop = asyncio.get_running_loop()
        if loop.is_running():
            loop.stop()

    def _pre_launch_checks(self):
        """Perform pre-launch checks to identify potential issues"""
        # Check git status
        if hasattr(self, 'git_manager') and self.git_manager:
            if not config.git.enabled:
                print("ℹ️ Git operations are disabled in config")
            else:
                print("Checking git status...")
                try:
                    if not self.git_manager.is_clean():
                        print("⚠️ Git workspace is not clean. You may encounter issues during block execution.")
                        print("   Consider committing or stashing your changes before proceeding.")
                        
                        # Check if auto-stash is enabled
                        auto_stash = config.safe_get('general', 'auto_stash', False)
                            
                        if auto_stash:
                            print("Auto-stash is enabled. Stashing changes...")
                            if self.git_manager.revert_changes():
                                print("✅ Changes successfully stashed.")
                            else:
                                print("❌ Failed to stash changes. Please clean your git workspace manually.")
                    else:
                        print("✅ Git workspace is clean")
                except Exception as e:
                    print(f"⚠️ Git status check failed: {e}")
        else:
            print("ℹ️ Git support not available")
            
            # Check background tasks configuration
        print("\nBackground Tasks:")
        if config.safe_get('general', 'run_tests_in_background', False):
            print("✅ Background test runner is enabled")
        else:
            print("ℹ️ Background test runner is disabled (enable with general.run_tests_in_background=true in config)")
        
        print("✅ Background file indexer is enabled")
        
        # Check directory structure
        print("\nFile System:")
        try:
            project_files = self.project_files.get_all_summaries()
            file_count = len(project_files.get("files", {}))
            print(f"✅ Indexed {file_count} files")
        except Exception as e:
            print(f"⚠️ File indexing error: {e}")
            
        # Check for UI configuration 
        print("\nUI Configuration:")
        component_count = len(getattr(self.server.component_registry, 'components', []))
        print(f"✅ Configured {component_count} UI components")
        
        # Only try to access message_handlers if the attribute exists
        handler_count = 0
        if hasattr(self.server, 'message_handlers'):
            handler_count = len(self.server.message_handlers)
        else:
            # Otherwise count our registered handlers
            handler_count = len(self._get_registered_handler_count())
        print(f"✅ Registered {handler_count} message handlers")
        
    def _get_registered_handler_count(self):
        """Count the number of registered message handlers"""
        handlers = []
        # Add component handlers
        for component in [self.chat_panel, self.protoblock_view, 
                         self.file_diff_view, self.git_view, self.speech_input]:
            if hasattr(component, 'message_handlers'):
                handlers.extend(component.message_handlers.keys())
        # Add our legacy handlers
        handlers.extend(["mic_click", "block_click", "file_diff_request", 
                        "file_status_request", "git_branch_request", 
                        "git_commit_request", "git_discard_request", 
                        "git_merge_request"])
        return handlers

    async def handle_error(self, error, source_method=None, component=None, notify_user=True):
        """
        Centralized error handler for UI operations.
        
        Args:
            error: The exception that occurred
            source_method: Optional name of the method where the error occurred
            component: Optional name of the component where the error occurred
            notify_user: Whether to notify the user about the error
        """
        # Generate error message
        error_text = str(error)
        source = f" in {source_method}" if source_method else ""
        component_text = f" ({component})" if component else ""
        
        # Log error to console
        print(f"Error{source}{component_text}: {error_text}")
        if config.safe_get('debug', 'show_traceback', True):
            traceback.print_exc()
        
        # Send status message
        await self.send_status_message(f"❌ Error{component_text}: {error_text[:100]}{'...' if len(error_text) > 100 else ''}")
        
        # Notify user via chat panel if requested
        if notify_user and self.chat_panel:
            try:
                await self.chat_panel.send_error_message(
                    f"An error occurred{component_text}: {error_text}"
                )
            except Exception as notify_err:
                print(f"Failed to send error notification: {notify_err}")
                
        return False

    async def cancel_background_tasks(self):
        """Cancel all running background tasks"""
        for task_name, task in list(self._background_tasks.items()):
            if not task.done():
                print(f"Cancelling background task: {task_name}")
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    print(f"Task {task_name} cancelled successfully")
                except Exception as e:
                    print(f"Error cancelling task {task_name}: {e}")
        self._background_tasks.clear()
    
    async def cleanup_components(self):
        """Clean up all UI components before shutdown"""
        components = [
            self.chat_panel, 
            self.protoblock_view, 
            self.file_diff_view, 
            self.git_view, 
            self.speech_input
        ]
        
        for component in components:
            try:
                if hasattr(component, 'cleanup') and callable(component.cleanup):
                    await component.cleanup()
            except Exception as e:
                print(f"Error cleaning up component {component.__class__.__name__}: {e}")
                
        # Reset recording state if active
        if self.is_recording:
            self.is_recording = False
                
    async def shutdown(self):
        """Perform graceful shutdown of the UI manager"""
        print("Shutting down UI Manager...")
        
        # Cancel background tasks
        await self.cancel_background_tasks()
        
        # Clean up components
        await self.cleanup_components()
        
        # Close websocket if open
        if self.websocket and not self.websocket.closed:
            await self.websocket.close()
            
        print("UI Manager shutdown complete")