import asyncio
import json
import websockets
import socket
import os
import signal
import subprocess
import argparse
import traceback
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
        # Config is already initialized when imported

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
                "write_files": protoblock.write_files,
                "context_files": protoblock.context_files,
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
        if not config.git.enabled:
            await self.send_status_message("Git operations are disabled in config.")
            return True
            
        await self.send_status_message("Checking git status...")
        git_manager = create_git_manager()
        
        if not git_manager.is_clean():
            await self.send_status_message("❌ Git workspace is not clean. Please commit or stash your changes before proceeding.")
            
            if config.safe_get('general', 'auto_stash', default=False):
                await self.send_status_message("Auto-stash is enabled. Stashing changes...")
                if git_manager.revert_changes():
                    await self.send_status_message("✅ Changes successfully stashed.")
                    return True
                else:
                    await self.send_status_message("❌ Failed to stash changes. Please clean your git workspace manually.")
                    return False
            else:
                await self.send_status_message("Please commit or stash your changes before proceeding.")
                return False
        
        await self.send_status_message("✅ Git workspace is clean.")
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

    async def handle_connection(self, websocket):
        self.websocket = websocket
        self._loop = asyncio.get_running_loop()
        
        # Start the status queue processor right away and save it as instance variable
        self._status_processor = asyncio.create_task(self._process_status_queue())
        
        # Send initial status
        await self.send_status_message("Connected. Initializing...")
        
        # Check git status early
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

            config_overrides = {
                'no_git': False,
                'json': None,
                'image': None
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
            asyncio.run(self.run_server())
        except KeyboardInterrupt:
            print("WebSocket server stopped by user.")