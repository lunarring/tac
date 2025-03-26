import asyncio
import random
import string
import websockets

async def handle_connection(websocket):
    while True:
        try:
            # Generate a random 10-character string
            msg = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
            await websocket.send(msg)
            await asyncio.sleep(1)
        except websockets.exceptions.ConnectionClosed:
            break
        except Exception as e:
            print(f"Error in connection handler: {e}")
            break

async def run_server():
    server = await websockets.serve(handle_connection, 'localhost', 8765)
    print("WebSocket server started on ws://localhost:8765")
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