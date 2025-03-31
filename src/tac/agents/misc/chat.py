import asyncio
import json
import websockets
import socket
import os
import signal
import subprocess

from tac.core.llm import LLMClient, Message
from tac.utils.project_files import ProjectFiles

def load_high_level_summaries():
    pf = ProjectFiles(".")
    data = pf.get_all_summaries()
    formatted_strings = []
    for rel_path, file_info in data.get("files", {}).items():
        if "error" in file_info:
            summary = f"Error analyzing file: {file_info['error']}"
        else:
            summary = file_info.get("summary_high_level", "No summary available")
        formatted_strings.append(f"###FILE: {rel_path}\n{summary}\n###END_FILE")
    return "\n\n".join(formatted_strings)

class ChatAgent:
    def __init__(self):
        self.client = LLMClient(llm_type="weak")
        # Prepare system prompt with file summaries for broader context
        file_summaries = load_high_level_summaries()
        system_content = (
            "You are a senior coding god. You are replying a bit sassy and sarcastic. "
            "You are also a bit of a know it all.  A high level summary of the codebase that the user wants to modify is here: "
            f"{file_summaries}. Always reply concise and without formatting. You help the user to find out what they want to be implemented "
            "and you always try to be brief and concise and help the planning. Remember, the user is not the one who is implementing the code, "
            "it is actually you and your team of AI agents and trusty agents. So don't tell the user how to do it themselves, but rather try to "
            "gather information about what the user wants to build in the context of the codebase above."
        )
        self.system_prompt = Message(role="system", content=system_content)

    async def handle_connection(self, websocket):
        # Initialize conversation with the system prompt
        conversation = [self.system_prompt]
        while True:
            try:
                user_input = await websocket.recv()
                print("Received message from client:", user_input)
                if user_input.strip():
                    # Insert the new user message at the beginning following the system prompt
                    conversation.insert(1, Message(role="user", content=user_input))
                    ai_response = self.client.chat_completion(conversation)
                    # Try to parse the AI response assuming JSON format with a content field
                    try:
                        parsed = json.loads(ai_response)
                        if isinstance(parsed, dict) and "content" in parsed:
                            extracted_content = parsed["content"]
                        else:
                            extracted_content = ai_response
                    except Exception:
                        extracted_content = ai_response
                    # Insert the assistant's response into the conversation
                    conversation.insert(1, Message(role="assistant", content=extracted_content))
                    print(f"Sending message to client: {extracted_content}")
                    await websocket.send(extracted_content)
            except websockets.exceptions.ConnectionClosed:
                break
            except Exception as e:
                print(f"Error in processing message: {e}")
                break

async def run_chat_server(host='localhost', port=8765):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((host, port))
            s.close()
    except OSError:
        try:
            result = subprocess.run(['pgrep', '-f', 'python.*tac'], capture_output=True, text=True)
            if result.stdout.strip():
                pids = result.stdout.strip().split('\n')
                for pid_str in pids:
                    try:
                        pid = int(pid_str)
                        print(f"Killing existing Python process (PID: {pid}) using port {port}")
                        os.kill(pid, signal.SIGTERM)
                    except Exception as e:
                        print(f"Failed to kill process {pid_str}: {e}")
                await asyncio.sleep(1)
            else:
                print(f"Port {port} is in use but no Python TAC processes found. Please free the port manually.")
                raise OSError(f"Port {port} is in use by non-Python process")
        except Exception as e:
            print(f"Failed to kill existing processes: {e}")

    chat_agent = ChatAgent()
    server = await websockets.serve(chat_agent.handle_connection, host, port)
    print(f"WebSocket server started on ws://{host}:{port}")
    print("Please open the UI to connect.")
    try:
        await asyncio.Future()  # Run indefinitely
    except asyncio.CancelledError:
        server.close()
        await server.wait_closed()
        raise

def launch_chat():
    try:
        asyncio.run(run_chat_server())
    except KeyboardInterrupt:
        print("WebSocket server stopped by user.")