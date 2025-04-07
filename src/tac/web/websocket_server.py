import asyncio
import json
import websockets
import socket
import os
import signal
import subprocess
import traceback
from typing import Callable, Dict, Optional, Any, List, Set
from tac.web.ui_components import ComponentRegistry, StatusBar


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
        
        # Component registry for UI components
        self.component_registry = ComponentRegistry()
        
        # Legacy message handlers for backwards compatibility
        self._message_handlers: Dict[str, Callable] = {}
        self._connection_handlers: List[Callable] = []
        self._disconnection_handlers: List[Callable] = []
        self._background_tasks = {}
        
        # Create and register core components
        self.status_bar = StatusBar()
        self.component_registry.register_component(self.status_bar)

    def register_component(self, component):
        """Register a UI component with the server"""
        self.component_registry.register_component(component)
        
    def register_message_type(self, message_type: str, component):
        """Register a component to handle a specific message type"""
        self.component_registry.register_message_type(message_type, component)

    def register_message_handler(self, message_type: str, handler: Callable):
        """Register a handler for a specific message type (legacy method)"""
        self._message_handlers[message_type] = handler

    def register_connection_handler(self, handler: Callable):
        """Register a handler to be called when a new connection is established (legacy method)"""
        self._connection_handlers.append(handler)

    def register_disconnection_handler(self, handler: Callable):
        """Register a handler to be called when a connection is closed (legacy method)"""
        self._disconnection_handlers.append(handler)

    def send_status_bar(self, message: str):
        """
        Safe method to update the status bar from any context (sync or async).
        Can be called from both the main thread and background threads.
        """
        self.status_bar.send_status_bar(message)

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
        await self.status_bar.send_status_message(message)

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
        
        # Set the websocket for all components
        self.component_registry.set_websocket_for_all(websocket)
        
        # Start components that need initialization
        await self.component_registry.start_components()
        
        # Call all registered connection handlers (legacy)
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
                        
                        if isinstance(data, dict):
                            # First try to route through component system
                            if "type" in data:
                                await self.component_registry.handle_message(data)
                                
                            # Also send to legacy handlers if registered
                            message_type = data.get("type")
                            if message_type in self._message_handlers:
                                handler = self._message_handlers[message_type]
                                if asyncio.iscoroutinefunction(handler):
                                    await handler(websocket, data)
                                else:
                                    handler(websocket, data)
                        else:
                            # Plain text message - send to user_message handler if exists
                            if "user_message" in self._message_handlers:
                                message_data = {"type": "user_message", "message": user_input_raw.strip()}
                                await self._message_handlers["user_message"](websocket, message_data)
                                
                                # Also route through component system
                                await self.component_registry.handle_message(message_data)
                    except json.JSONDecodeError:
                        # Plain text message
                        if "user_message" in self._message_handlers:
                            message_data = {"type": "user_message", "message": user_input_raw.strip()}
                            await self._message_handlers["user_message"](websocket, message_data)
                            
                            # Also route through component system
                            await self.component_registry.handle_message(message_data)
                        
                except websockets.exceptions.ConnectionClosed:
                    break
                except Exception as e:
                    print(f"Error in processing message: {e}")
                    traceback.print_exc()
                    
        finally:
            # Stop all components that need cleanup
            await self.component_registry.stop_components()
            
            # Call all registered disconnection handlers (legacy)
            for handler in self._disconnection_handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(websocket)
                    else:
                        handler(websocket)
                except Exception as e:
                    print(f"Error in disconnection handler: {e}")
            
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