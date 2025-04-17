import asyncio
import json
import websockets
import socket
import os
import signal
import subprocess
import traceback
import http.server
import threading
import socketserver
import webbrowser
from pathlib import Path
from typing import Callable, Dict, Optional, Any, List, Set
from tac.web.ui_components import ComponentRegistry, StatusBar
import tempfile


class TACHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler that serves the UI HTML file directly"""
    
    def __init__(self, *args, base_path=None, index_html=None, **kwargs):
        self.base_path = base_path
        self.index_html = index_html
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        """Handle GET requests by serving the UI files"""
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            with open(self.index_html, 'rb') as file:
                self.wfile.write(file.read())
        elif self.path.startswith('/screenshots/'):
            # Handle screenshot requests
            self.serve_screenshot(self.path[12:])  # Remove '/screenshots/' prefix
        else:
            # For other files (CSS, JS, etc.), try to serve from base_path
            try:
                # Get requested file path relative to web directory
                file_path = Path(self.base_path) / self.path.lstrip('/')
                if file_path.exists() and file_path.is_file():
                    self.send_response(200)
                    # Set content type based on file extension
                    if file_path.suffix == '.css':
                        self.send_header('Content-type', 'text/css')
                    elif file_path.suffix == '.js':
                        self.send_header('Content-type', 'application/javascript')
                    else:
                        self.send_header('Content-type', 'application/octet-stream')
                    self.end_headers()
                    with open(file_path, 'rb') as file:
                        self.wfile.write(file.read())
                else:
                    self.send_error(404, "File not found")
            except Exception as e:
                self.send_error(500, str(e))
    
    def serve_screenshot(self, screenshot_path):
        """
        Serve a screenshot file from anywhere on the filesystem.
        
        Args:
            screenshot_path: The full path to the screenshot, or a relative path from /tmp
        """
        try:
            # Handle absolute and relative paths
            if screenshot_path.startswith('/'):
                # Absolute path
                file_path = screenshot_path
            else:
                # Check common locations for temp files
                tmp_locations = [
                    os.path.join('/tmp', screenshot_path),
                    os.path.join(os.path.expanduser('~'), '.tac', 'tmp', screenshot_path),
                    os.path.join(tempfile.gettempdir(), screenshot_path)
                ]
                
                # Try each location
                file_path = None
                for loc in tmp_locations:
                    if os.path.exists(loc):
                        file_path = loc
                        break
                
                # If not found in known locations, try as a relative path
                if not file_path:
                    relative_path = os.path.join(os.getcwd(), screenshot_path)
                    if os.path.exists(relative_path):
                        file_path = relative_path
                    else:
                        # Last resort - use as is
                        file_path = screenshot_path
            
            # Log attempt
            print(f"Attempting to serve screenshot: {file_path}")
            
            # Check if file exists
            if not os.path.exists(file_path):
                print(f"Screenshot not found: {file_path}")
                self.send_error(404, f"Screenshot not found: {file_path}")
                return
            
            # Get file size for logging
            file_size = os.path.getsize(file_path)
            print(f"Screenshot found: {file_path} ({file_size} bytes)")
            
            # Determine content type based on extension
            content_type = "image/png"  # Default to PNG
            if file_path.lower().endswith('.jpg') or file_path.lower().endswith('.jpeg'):
                content_type = "image/jpeg"
            
            # Serve the file
            with open(file_path, 'rb') as f:
                file_data = f.read()
                
            self.send_response(200)
            self.send_header('Content-type', content_type)
            self.send_header('Content-length', str(len(file_data)))
            self.end_headers()
            self.wfile.write(file_data)
            print(f"Successfully served screenshot: {file_path} ({len(file_data)} bytes)")
            
        except Exception as e:
            print(f"Error serving screenshot: {e}")
            import traceback
            traceback.print_exc()
            self.send_error(500, str(e))


class WebSocketServer:
    """
    WebSocket server that handles connections, message routing and server lifecycle.
    This class extracts the WebSocket functionality from UIManager to separate concerns.
    """
    # Add static list to track instances
    active_instances = []
    
    def __init__(self, host: str = 'localhost', port: int = 8765, auto_find_port: bool = True):
        self.host = host
        self.requested_port = port
        self.port = port  # Will be updated if auto_find_port is True
        self.auto_find_port = auto_find_port
        self.websocket = None
        self._loop = None
        self.http_server = None
        self.http_port = None
        
        # Register active instances
        WebSocketServer.active_instances.append(self)
        
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

    def find_free_port(self, start_port=None):
        """Find a free port starting from the specified port"""
        if start_port is None:
            start_port = self.requested_port
            
        port = start_port
        max_attempts = 100  # Limit the search to 100 ports
        
        for _ in range(max_attempts):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind((self.host, port))
                    s.close()
                    return port
            except OSError:
                # Port is in use, try the next one
                port += 1
                
        # If we reach here, we couldn't find a free port
        raise RuntimeError(f"Could not find a free port after {max_attempts} attempts.")
    
    def start_http_server(self):
        """Start an HTTP server to serve the UI files"""
        # Find the index.html file
        module_dir = Path(os.path.dirname(os.path.abspath(__file__)))
        index_html = module_dir / "index.html"
        
        if not index_html.exists():
            print(f"Warning: index.html not found at {index_html}. UI may not work properly.")
            return False
            
        # Find a free port for HTTP, starting at WS port + 1 
        self.http_port = self.find_free_port(self.port + 1)
        
        # Create a handler that knows about the base path and index file
        handler = lambda *args, **kwargs: TACHTTPRequestHandler(
            *args, 
            base_path=module_dir,
            index_html=index_html,
            **kwargs
        )
        
        # Start the HTTP server in a separate thread
        self.http_server = socketserver.TCPServer((self.host, self.http_port), handler)
        thread = threading.Thread(target=self.http_server.serve_forever)
        thread.daemon = True
        thread.start()
        
        print(f"HTTP server started on http://{self.host}:{self.http_port}")
        print(f"Screenshots will be served via: http://{self.host}:{self.http_port}/screenshots/{{path}}")
        return True

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
        
        # Send port information immediately after connection
        try:
            port_info = {
                "type": "server_info",
                "ws_port": self.port,
                "http_port": self.http_port
            }
            await websocket.send(json.dumps(port_info))
            print(f"Sent port information to client: WS={self.port}, HTTP={self.http_port}")
        except Exception as e:
            print(f"Error sending port information: {e}")
        
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
                                # Filter out recording_status messages from chat
                                if data.get("type") == "recording_status":
                                    # Make sure component_id is set to speech_input
                                    if "component_id" not in data:
                                        data["component_id"] = "speech_input"
                                    # Only route these to the specific component, not to all handlers
                                    speech_input = self.component_registry.get_component("speech_input")
                                    if speech_input:
                                        await speech_input.handle_message(data)
                                    # Explicitly NEVER route recording_status messages to legacy handlers
                                    # which would cause them to show up in chat
                                else:
                                    # For other message types, route to both systems
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
                                # No message type - handle as legacy
                                print("Message with no type received:", data)
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
            # Find a free port if auto_find_port is enabled
            if self.auto_find_port:
                self.port = self.find_free_port()
                if self.port != self.requested_port:
                    print(f"Requested port {self.requested_port} is in use, using port {self.port} instead.")
            else:
                # Check if port is in use
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.bind((self.host, self.port))
                        s.close()
                except OSError:
                    print(f"Port {self.port} is already in use. Please select a different port.")
                    raise
            
            # Start the HTTP server to serve the UI
            self.start_http_server()
            
            # Start the WebSocket server
            server = await websockets.serve(self.handle_connection, self.host, self.port)
            print(f"WebSocket server started on ws://{self.host}:{self.port}")
            ui_url = f"http://{self.host}:{self.http_port}"
            print(f"Please open {ui_url} in your browser to view the UI.")
            
            # Automatically open browser in a separate thread to avoid blocking
            print("Attempting to open browser automatically...")
            threading.Thread(target=lambda: webbrowser.open(ui_url)).start()
            
            # Use a different approach that allows for proper cancellation
            stop_event = asyncio.Event()
            
            def signal_handler():
                stop_event.set()
                
            # Add signal handlers for graceful shutdown
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, signal_handler)
                
            try:
                # Wait until stopped
                await stop_event.wait()
            finally:
                # Clean up
                if self.http_server:
                    self.http_server.shutdown()
                    self.http_server = None
                
                server.close()
                await server.wait_closed()
                
                # Remove from active instances
                if self in WebSocketServer.active_instances:
                    WebSocketServer.active_instances.remove(self)
        
        except Exception as e:
            print(f"Error starting WebSocket server: {e}")
            # Clean up HTTP server if it was started
            if self.http_server:
                self.http_server.shutdown()
                self.http_server = None
            
            # Remove from active instances
            if self in WebSocketServer.active_instances:
                WebSocketServer.active_instances.remove(self)
                
            # Re-raise the exception
            raise

    def launch(self):
        """Start the WebSocket server"""
        loop = self._get_loop()
        try:
            loop.run_until_complete(self.run_server())
        except KeyboardInterrupt:
            print("WebSocket server stopped by user")
        except Exception as e:
            print(f"Error in WebSocket server: {e}")
            traceback.print_exc()
        finally:
            # Close any lingering tasks
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
                
            # Remove from active instances on shutdown
            if self in WebSocketServer.active_instances:
                WebSocketServer.active_instances.remove(self) 