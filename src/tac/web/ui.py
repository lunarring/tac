import asyncio
import json
import websockets
import socket
import os
import signal
import subprocess
from tac.core.llm import LLMClient, Message

async def handle_connection(websocket):
    client = LLMClient(llm_type="weak")
    # Initialize conversation with the new system prompt
    system_prompt = Message(role="system", content="You are a senior coding god")
    conversation = [system_prompt]
    # Immediately send the system prompt message upon connection
    await websocket.send(system_prompt.content)
    while True:
        try:
            user_input = await websocket.recv()
            print("Received message from client:", user_input)
            if user_input.strip():
                conversation.append(Message(role="user", content=user_input))
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
                # Append the assistant's response to the conversation and send only its raw content
                conversation.append(Message(role="assistant", content=extracted_content))
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