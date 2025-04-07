import asyncio
import json
import websockets
import socket
import os
import signal
import subprocess
import traceback
from typing import Callable, Dict, Optional, Any, List


class WebSocketServer:
    """
    WebSocket server that handles connections, message routing and server lifecycle.
    This class extracts the WebSocket functionality from UIManager to separate concerns.
    """
    def __init__(self, host: str = 'localhost', port: int = 8765):
        self.host = host
        self.port = port
        self.websocket = None
        self._loop = None
        self._status_queue = asyncio.Queue()
        self._status_lock = asyncio.Lock()
        self._status_processor = None
        self._message_handlers: Dict[str, Callable] = {}
        self._connection_handlers: List[Callable] = []
        self._disconnection_handlers: List[Callable] = []
        self._background_tasks = {}

    def register_message_handler(self, message_type: str, handler: Callable):
        """Register a handler for a specific message type"""
        self._message_handlers[message_type] = handler

    def register_connection_handler(self, handler: Callable):
        """Register a handler to be called when a new connection is established"""
        self._connection_handlers.append(handler)

    def register_disconnection_handler(self, handler: Callable):
        """Register a handler to be called when a connection is closed"""
        self._disconnection_handlers.append(handler)

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

    def send_status_bar(self, message: str):
        """
        Safe method to update the status bar from any context (sync or async).
        Can be called from both the main thread and background threads.
        """
        print(f"Status update requested: {message}")
        if self._loop and self._loop.is_running():
            try:
                # If we're in an async context with a running loop
                asyncio.run_coroutine_threadsafe(self._status_queue.put(message), self._loop)
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

    def _get_loop(self):
        """Get the current event loop or create a new one"""
        if self._loop is None:
            try:
                self._loop = asyncio.get_event_loop()
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
        return self._loop

    async def send_status_message(self, message: str):
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

    async def send_message(self, data: dict):
        """Send a JSON message to the connected client"""
        if self.websocket:
            try:
                await self.websocket.send(json.dumps(data))
                return True
            except Exception as e:
                print(f"Error sending message: {e}")
                return False
        return False

    async def handle_connection(self, websocket):
        """Handle a new WebSocket connection"""
        self.websocket = websocket
        self._loop = asyncio.get_running_loop()
        
        # Start the status queue processor right away
        self._status_processor = asyncio.create_task(self._process_status_queue())
        
        # Call all registered connection handlers
        for handler in self._connection_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(websocket)
                else:
                    handler(websocket)
            except Exception as e:
                print(f"Error in connection handler: {e}")
        
        try:
            while True:
                try:
                    user_input_raw = await websocket.recv()
                    print("Received message from client:", user_input_raw)
                    
                    try:
                        data = json.loads(user_input_raw)
                        if isinstance(data, dict) and "type" in data:
                            message_type = data["type"]
                            if message_type in self._message_handlers:
                                handler = self._message_handlers[message_type]
                                if asyncio.iscoroutinefunction(handler):
                                    await handler(websocket, data)
                                else:
                                    handler(websocket, data)
                            else:
                                print(f"No handler registered for message type: {message_type}")
                        else:
                            # Plain text message
                            if "user_message" in self._message_handlers:
                                await self._message_handlers["user_message"](websocket, {"type": "user_message", "message": user_input_raw.strip()})
                    except json.JSONDecodeError:
                        # Plain text message
                        if "user_message" in self._message_handlers:
                            await self._message_handlers["user_message"](websocket, {"type": "user_message", "message": user_input_raw.strip()})
                        
                except websockets.exceptions.ConnectionClosed:
                    break
                except Exception as e:
                    print(f"Error in processing message: {e}")
                    traceback.print_exc()
                    
        finally:
            # Call all registered disconnection handlers
            for handler in self._disconnection_handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(websocket)
                    else:
                        handler(websocket)
                except Exception as e:
                    print(f"Error in disconnection handler: {e}")
            
            # Cancel the status processor when connection is closed
            if self._status_processor:
                self._status_processor.cancel()
                try:
                    await self._status_processor
                except asyncio.CancelledError:
                    pass
            
            # Cancel all background tasks
            for task_name, task in self._background_tasks.items():
                if not task.done():
                    print(f"Cancelling background task: {task_name}")
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            
            # Clear websocket reference
            self.websocket = None

    async def run_server(self):
        """Run the WebSocket server"""
        try:
            # Check if port is in use
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind((self.host, self.port))
                s.close()
        except OSError:
            # Port is in use, try to kill existing process
            try:
                result = subprocess.run(['pgrep', '-f', 'python.*tac'], capture_output=True, text=True)
                if result.stdout.strip():
                    pids = result.stdout.strip().split('\n')
                    for pid_str in pids:
                        try:
                            pid = int(pid_str)
                            print(f"Killing existing Python process (PID: {pid}) using port {self.port}")
                            os.kill(pid, signal.SIGTERM)
                        except Exception as e:
                            print(f"Failed to kill process {pid_str}: {e}")
                    await asyncio.sleep(1)
                else:
                    print(f"Port {self.port} is in use but no Python TAC processes found. Please free the port manually.")
                    raise OSError(f"Port {self.port} is in use by non-Python process")
            except Exception as e:
                print(f"Failed to kill existing processes: {e}")

        # Start the WebSocket server
        server = await websockets.serve(self.handle_connection, self.host, self.port)
        print(f"WebSocket server started on ws://{self.host}:{self.port}")
        print("Please open 'src/tac/web/index.html' in your browser to view the UI.")
        
        try:
            await asyncio.Future()  # Run forever
        except asyncio.CancelledError:
            server.close()
            await server.wait_closed()
            raise

    def launch(self):
        """Start the WebSocket server"""
        try:
            asyncio.run(self.run_server())
        except KeyboardInterrupt:
            print("WebSocket server stopped by user.") 