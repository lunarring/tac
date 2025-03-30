import asyncio
import random
import string
import json
import websockets
import socket
import os
import signal
import subprocess

async def handle_connection(websocket):
    async def send_messages():
        while True:
            try:
                # Generate a random 10-character string
                random_str = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
                # Format the message as a JSON object with type and content keys
                msg = json.dumps({"type": "chat", "content": random_str})
                await websocket.send(msg)
                await asyncio.sleep(1)
            except websockets.exceptions.ConnectionClosed:
                break
            except Exception as e:
                print(f"Error in sending messages: {e}")
                break

    async def receive_messages():
        while True:
            try:
                message = await websocket.recv()
                print("Received message from client:", message)
            except websockets.exceptions.ConnectionClosed:
                break
            except Exception as e:
                print(f"Error in receiving messages: {e}")
                break

    send_task = asyncio.create_task(send_messages())
    receive_task = asyncio.create_task(receive_messages())
    done, pending = await asyncio.wait([send_task, receive_task], return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()

async def run_server():
    # Check if port is in use and handle it
    try:
        # Try to create a socket to check if port is already in use
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('localhost', 8765))
            s.close()
    except OSError:
        # Port is in use, find and kill the process
        try:
            # Find Python processes using the port
            result = subprocess.run(['pgrep', '-f', 'python.*tac'], capture_output=True, text=True)
            if result.stdout.strip():
                # Handle multiple PIDs
                pids = result.stdout.strip().split('\n')
                for pid_str in pids:
                    try:
                        pid = int(pid_str)
                        print(f"Killing existing Python process (PID: {pid}) using port 8765")
                        os.kill(pid, signal.SIGTERM)
                    except Exception as e:
                        print(f"Failed to kill process {pid_str}: {e}")
                # Wait a moment for the port to be released
                await asyncio.sleep(1)
            else:
                print("Port 8765 is in use but no Python TAC processes found. Please free the port manually.")
                raise OSError("Port 8765 is in use by non-Python process")
        except Exception as e:
            print(f"Failed to kill existing processes: {e}")

    # Start the server
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