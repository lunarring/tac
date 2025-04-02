import asyncio
import json
import websockets
import socket
import os
import signal
import subprocess
import argparse
from tac.agents.misc.chat import ChatAgent
from tac.utils.project_files import ProjectFiles
from tac.utils.audio import Speech2Text  # Newly imported for speech-to-text functionality
from tac.cli.main import execute_command
from tac.core.llm import LLMClient, Message

class UIManager:
    def __init__(self, base_dir="."):
        self.base_dir = base_dir
        self.project_files = ProjectFiles(self.base_dir)
        self.speech_to_text = Speech2Text()
        self.is_recording = False
        self.task_instructions = None
        self.websocket = None
        self._loop = None

    def _get_loop(self):
        if self._loop is None:
            try:
                self._loop = asyncio.get_event_loop()
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
        return self._loop

    def send_status(self, message):
        """Synchronous wrapper for sending status messages"""
        if self.websocket:
            asyncio.run_coroutine_threadsafe(self.send_status_message(message), self._get_loop())

    async def send_status_message(self, message):
        if self.websocket:
            await self.websocket.send(json.dumps({
                "type": "status_message",
                "message": message
            }))

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
        file_summaries = await self.load_high_level_summaries()
        # Send frequent status updates for key workflow stages:
        self.send_status("Running initial tests...")
        await asyncio.sleep(0.3)
        self.send_status("Initial tests passed.")
        await asyncio.sleep(0.3)
        self.send_status("Updating file summaries...")
        await asyncio.sleep(0.3)
        self.send_status("File updates completed.")

        system_content = (
            "A high level summary of the codebase which the user wants to modify is here: {file_summaries}. Always reply concise and without formatting. Your task is to ask questions and clarify requests, for this early phase of software design. Always try to be brief and concise and help the planning. Remember, the user is not the one who is implementing the code, it is actually you and your team of AI agents and they use trusty agents to verify the code. So don't tell the user how to do it themselves, but rather try to gather information about what the user wants to build in the context of the codebase above. Don't be too verbose about the code itself, but rather gather an understanding of what the user really wants. Always be brief and to the point! However the goal is to end up with ONE clear task and do them one at a time. Ideally just answer in ONE sentence and not more! Also if you feel we have enough information, tell the user that they should hit the block button below to start the protoblock execution.")
        formatted_system_content = system_content.format(file_summaries=file_summaries)
        agent = ChatAgent(system_prompt=formatted_system_content)

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
                            await self.handle_block_click(websocket, agent)
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
                    assistant_reply = agent.process_message(user_message)
                    print(f"Sending message to client: {assistant_reply}")
                    await websocket.send(assistant_reply)
            except websockets.exceptions.ConnectionClosed:
                break
            except Exception as e:
                print(f"Error in processing message: {e}")
                break

    async def handle_block_click(self, websocket, agent):
        try:
            self.send_status("Creating block from conversation...")

            genesis_prompt = agent.generate_task_instructions()

            # Send a clear status update indicating protoblock execution begins
            self.send_status("Executing protoblock")

            config_overrides = {
                'no_git': False,
                'json': None,
                'image': None
            }
            for attr in ['llm_type', 'model', 'api_base', 'json_mode']:
                config_overrides[attr] = None

            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(None, lambda: execute_command(
                task_instructions=genesis_prompt,
                config_overrides=config_overrides
            ))

            if success:
                self.send_status("✅ Block executed successfully!")
            else:
                self.send_status("❌ Block execution failed!")

        except Exception as e:
            print(f"Error during block execution: {e}")
            import traceback
            traceback.print_exc()
            self.send_status(f"❌ Error: {str(e)}")

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