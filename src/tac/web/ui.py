import asyncio
import random
import string
import json
import websockets

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