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

async def handle_connection(websocket):
    client = LLMClient(llm_type="weak")
    # Retrieve high-level file summaries from the project
    file_summaries = load_high_level_summaries()
    # Incorporate the file summaries into the system prompt for broader context
    system_content = ("You are a senior coding god. You are replying a bit sassy and sarcastic. "
                      "You are also a bit of a know it all. You help the user to find out what they want to code "
                      "and you always try to be brief and concise and help the planning. Never show me any code however.\n\n"
                      "Project File Summaries:\n" + file_summaries)
    # Initialize conversation with the new system prompt
    system_prompt = Message(role="system", content=system_content)
    conversation = [system_prompt]
    # Do not send the system prompt to the client UI

    while True:
        try:
            user_input = await websocket.recv()
            print("Received message from client:", user_input)
            if user_input.strip():
                # Insert the new user message at the beginning of the conversation (after system prompt)
                conversation.insert(1, Message(role="user", content=user_input))
                ai_response = client.chat_completion(conversation)
                # Extract only the 'content' field from the AI response if it's in JSON format
                try:
                    parsed = json.loads(ai_response)
                    if isinstance(parsed, dict) and "content" in parsed:
                        extracted_content = parsed["content"]
                    else:
                        extracted_content = ai_response
                except Exception:
                    extracted_content = ai_response
                # Insert the assistant's response at the beginning of the conversation (after system prompt)
                conversation.insert(1, Message(role="assistant", content=extracted_content))
                print(f"Sending message to client: {extracted_content}")
                await websocket.send(extracted_content)
        except websockets.exceptions.ConnectionClosed:
            break
        except Exception as e:
            print(f"Error in processing message: {e}")
            break

async def run_server():
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

    server = await websockets.serve(handle_connection, 'localhost', 8765)
    print("WebSocket server started on ws://localhost:8765")
    print("Please open 'src/tac/web/index.html' in your browser to view the UI.")
    try:
        await asyncio.Future()  # Run forever
    except asyncio.CancelledError:
        server.close()
        await server.wait_closed()
        raise

def launch_ui():
    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        print("WebSocket server stopped by user.")