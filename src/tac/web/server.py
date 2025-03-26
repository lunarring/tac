import asyncio
import threading
import os
import time
import datetime
import http.server
import socketserver
import websockets

# HTTP Server settings
HTTP_PORT = 8000
WEBSOCKET_PORT = 8765

# Define an asynchronous websocket handler
async def ws_handler(websocket, path):
    print(f"New websocket connection: {websocket.remote_address}")
    try:
        while True:
            # Send dynamic content - current datetime string
            message = f"Server time: {datetime.datetime.now()}"
            await websocket.send(message)
            await asyncio.sleep(1)
    except websockets.exceptions.ConnectionClosed:
        print("Websocket connection closed.")

# Function to start a simple HTTP server to serve static files from this directory
def start_http_server():
    # Get the directory containing this file (and client.html)
    web_dir = os.path.abspath(os.path.dirname(__file__))
    os.chdir(web_dir)
    
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", HTTP_PORT), handler) as httpd:
        print(f"HTTP server serving at: http://localhost:{HTTP_PORT}")
        httpd.serve_forever()

# The main function to launch UI: starts both the HTTP and websocket servers
def launch_ui():
    # Start the HTTP server in a separate daemon thread
    http_thread = threading.Thread(target=start_http_server, daemon=True)
    http_thread.start()
    
    # Start the WebSocket server using asyncio event loop
    async def start_ws():
        async with websockets.serve(ws_handler, "localhost", WEBSOCKET_PORT):
            print(f"WebSocket server started at ws://localhost:{WEBSOCKET_PORT}")
            # Run forever
            await asyncio.Future()
            
    try:
        print("Launching UI server (HTTP and WebSocket)...")
        asyncio.run(start_ws())
    except KeyboardInterrupt:
        print("Shutting down UI server.")

# Expose launch_ui so that it can be imported as required.
if __name__ == "__main__":
    launch_ui()
    
# Also allow this module to be imported as ui_launcher
launch_ui  # This ensures that 'launch_ui' is a valid exported symbol.