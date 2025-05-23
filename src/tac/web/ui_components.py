import json
from typing import Dict, Any, Optional, Callable, List, Union
import asyncio


class Component:
    """
    Base class for UI components that can send and receive messages.
    """
    def __init__(self, component_id: str):
        self.component_id = component_id
        self.websocket = None
        self._message_handlers: Dict[str, Callable] = {}
        
    def register_message_handler(self, message_type: str, handler: Callable):
        """Register a handler for a specific message type"""
        self._message_handlers[message_type] = handler
        
    def set_websocket(self, websocket):
        """Set the websocket connection for this component"""
        self.websocket = websocket
        
    async def handle_message(self, message_data: Dict[str, Any]):
        """Handle a message sent to this component"""
        message_type = message_data.get("type")
        
        if message_type in self._message_handlers:
            handler = self._message_handlers[message_type]
            if asyncio.iscoroutinefunction(handler):
                await handler(message_data)
            else:
                handler(message_data)
        else:
            print(f"No handler registered for message type: {message_type} in component {self.component_id}")
            
    async def send_message(self, message_data: Dict[str, Any]):
        """Send a message to the client"""
        if self.websocket:
            # Always include component_id to ensure proper routing to the right component
            data = message_data.copy()
            
            # Only skip component_id for chat messages as they need special handling
            if "component_id" not in data:
                data["component_id"] = self.component_id
                
            # Prevent recording_status messages from being sent to chat
            # Only speech_input component should send recording_status messages
            if data.get("type") == "recording_status" and data.get("component_id") != "speech_input":
                print(f"Blocked recording_status message from being sent by non-speech_input component: {self.component_id}")
                return False
                
            # If this is speech_input component sending recording_status message
            # ensure it has the correct component_id to prevent chat display
            if self.component_id == "speech_input" and data.get("type") == "recording_status":
                data["component_id"] = "speech_input"
                
            try:
                await self.websocket.send(json.dumps(data))
                return True
            except Exception as e:
                print(f"Error sending message from component {self.component_id}: {e}")
                return False
        return False


class StatusBar(Component):
    """
    Component for displaying status messages in the UI.
    """
    def __init__(self):
        super().__init__("status_bar")
        self._status_queue = asyncio.Queue()
        self._status_lock = asyncio.Lock()
        self._status_processor = None
        
    async def start(self):
        """Start the status queue processor"""
        self._status_processor = asyncio.create_task(self._process_status_queue())
        
    async def stop(self):
        """Stop the status queue processor"""
        if self._status_processor:
            self._status_processor.cancel()
            try:
                await self._status_processor
            except asyncio.CancelledError:
                pass
            
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
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(self._status_queue.put(message), loop)
                print(f"Status message queued: {message}")
            else:
                # If no running loop, try to create one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._status_queue.put(message))
                print(f"Status message queued in new loop: {message}")
        except Exception as e:
            print(f"Error queueing status message: {e}")
            
    async def send_status_message(self, message: str):
        """Direct async method to send status messages with awaiting"""
        # Check if this is an attempt update message from the processor
        processor_attempt_match = None
        if "Starting block creation and execution attempt" in message:
            # Extract the attempt info from the processor log message
            processor_attempt_match = message.split("Starting block creation and execution attempt ")[1].split(" of ")
            if len(processor_attempt_match) == 2:
                current = processor_attempt_match[0]
                max_attempts = processor_attempt_match[1]
                # Update message to match the format in the processor - without emoji
                message = f"Retrying with modifications (execution cycle {current})"
        
        # Send the status message to the client
        await self.send_message({
            "type": "status_message",
            "message": message
        })
        
        # Also send an update to the block status display in the right panel
        # This helps users see the status even when focusing on the right panel
        # Special message format for updating the block header status
        component_id = "block_header"  # Target component in the HTML
        try:
            if self.websocket:
                block_status_data = {
                    "type": "update_block_status",
                    "component_id": component_id,
                    "status": message
                }
                await self.websocket.send(json.dumps(block_status_data))
        except Exception as e:
            print(f"Error sending block status update: {e}")
        
        print(f"Status update sent: {message}")  # Log sent messages


class ChatPanel(Component):
    """
    Component for handling chat interactions in the UI.
    """
    def __init__(self):
        super().__init__("chat_panel")
        
    async def handle_message(self, message_data: Dict[str, Any]):
        """Handle a message sent to this component"""
        message_type = message_data.get("type")
        
        # Ignore recording_status messages and execute_script messages
        if message_type == "recording_status" or message_data.get("ui_only") is True or message_type == "execute_script":
            return
            
        # Process other message types normally
        if message_type in self._message_handlers:
            handler = self._message_handlers[message_type]
            if asyncio.iscoroutinefunction(handler):
                await handler(message_data)
            else:
                handler(message_data)
        else:
            print(f"No handler registered for message type: {message_type} in component {self.component_id}")
        
    async def send_chat_message(self, message: str):
        """Send a chat message to the client"""
        # Frontend expects: { "type": "chat_message", "message": "..." }
        # without the component_id
        await self.send_message({
            "type": "chat_message",
            "message": message
        })
        
    async def send_error_message(self, message: str):
        """Send an error message to the client"""
        await self.send_message({
            "type": "error_message",
            "message": message
        })
        
    async def send_info_message(self, message: str):
        """Send an info message to the client"""
        await self.send_message({
            "type": "info_message",
            "message": message
        })


class ProtoBlockView(Component):
    """
    Component for displaying and managing ProtoBlock data.
    """
    def __init__(self, max_attempts: int = 4):
        super().__init__("protoblock_view")
        self.max_attempts = max_attempts
        
    async def send_protoblock_data(self, protoblock):
        """
        Send protoblock data to the client to display in the UI.
        
        Args:
            protoblock: The ProtoBlock object containing all the details
        """
        if not protoblock:
            return
            
        # Get attempt number from processor's idx_attempt in run_loop
        # Format attempt number using max_attempts from config
        attempt_number = f"{protoblock.attempt_number}/{self.max_attempts}"
        
        # Convert protoblock to a suitable JSON format for display
        protoblock_data = {
            "type": "protoblock_data",
            "attempt": attempt_number,
            "block_id": protoblock.block_id,
            "task_description": protoblock.task_description,
            "write_files": protoblock.write_files,
            "trusty_agents": protoblock.trusty_agents,
            "trusty_agent_prompts": protoblock.trusty_agent_prompts or {},
            "trusty_agent_results": protoblock.trusty_agent_results or {}
        }
        
        print(f"Sending protoblock data to client")
        await self.send_message(protoblock_data)
        print("Protoblock data sent successfully")
        
    async def remove_protoblock(self, message: str = ""):
        """Remove the protoblock from the UI"""
        await self.send_message({
            "type": "remove_protoblock",
            "message": message
        })


class FileDiffView(Component):
    """
    Component for displaying file diffs in the UI.
    """
    def __init__(self):
        super().__init__("file_diff_view")
        
    async def send_file_diff(self, filename: str, diff: str):
        """Send a file diff to the client"""
        await self.send_message({
            "type": "file_diff_response",
            "filename": filename,
            "diff": diff
        })
        
    async def send_file_status(self, filename: str, is_modified: bool, 
                               added_lines: int = 0, removed_lines: int = 0, 
                               error: Optional[str] = None):
        """Send file status information to the client"""
        message = {
            "type": "file_status_response",
            "filename": filename,
            "is_modified": is_modified,
            "added_lines": added_lines,
            "removed_lines": removed_lines
        }
        
        if error:
            message["error"] = error
            
        await self.send_message(message)
        
    async def send_error(self, filename: str, error_message: str):
        """Send an error message about a file to the client"""
        await self.send_message({
            "type": "file_diff_response",
            "filename": filename,
            "error": error_message
        })


class GitView(Component):
    """
    Component for displaying git-related information in the UI.
    """
    def __init__(self):
        super().__init__("git_view")
        
    async def send_branches(self, branches: List[str], error: Optional[str] = None):
        """Send list of git branches to the client"""
        message = {
            "type": "git_branch_response",
            "branches": branches
        }
        
        if error:
            message["error"] = error
            
        await self.send_message(message)
        
    async def send_operation_result(self, operation: str, success: bool, message: str):
        """Send the result of a git operation to the client"""
        await self.send_message({
            "type": "git_operation_response",
            "operation": operation,
            "success": success,
            "message": message
        })


class SpeechInput(Component):
    """
    Component for handling speech input button UI.
    """
    def __init__(self):
        super().__init__("speech_input")
        self._debug_mode = False  # Set to True to enable debug messages
        
    async def send_transcription(self, transcript: str):
        """Send a speech transcription to the client"""
        await self.send_message({
            "type": "transcribed_message",
            "message": transcript
        })
        
    async def send_recording_status(self, is_recording: bool):
        """
        Send recording status update to update the microphone button UI.
        When not in debug mode, this only updates the UI state without sending
        debug messages.
        """
        # This message should only go to the speech_input component, not the chat panel
        # Make sure component_id is explicitly set to ensure proper routing
        await self.send_message({
            "type": "recording_status",
            "is_recording": is_recording,
            "component_id": "speech_input",  # Explicitly set component_id
            "ui_only": True  # Mark as UI-only message to prevent it from being treated as chat
        })


class ComponentRegistry:
    """
    Registry to manage all UI components and handle message routing.
    """
    def __init__(self):
        self.components: Dict[str, Component] = {}
        self.message_type_handlers: Dict[str, List[Component]] = {}
        
    def register_component(self, component: Component):
        """Register a component with the registry"""
        self.components[component.component_id] = component
        
    def register_message_type(self, message_type: str, component: Component):
        """Register a component to handle a specific message type"""
        if message_type not in self.message_type_handlers:
            self.message_type_handlers[message_type] = []
        self.message_type_handlers[message_type].append(component)
        
    def set_websocket_for_all(self, websocket):
        """Set the websocket for all registered components"""
        for component in self.components.values():
            component.set_websocket(websocket)
            
    async def handle_message(self, message_data: Dict[str, Any]):
        """Route a message to the appropriate component(s)"""
        message_type = message_data.get("type")
        component_id = message_data.get("component_id")
        
        # Special case for recording_status messages - only send to speech_input
        if message_type == "recording_status" or message_data.get("ui_only") is True:
            speech_input = self.get_component("speech_input")
            if speech_input:
                await speech_input.handle_message(message_data)
            return
        
        # Special case for chat messages - ensure they go to chat panel regardless of component_id
        if message_type == "chat_message":
            chat_panel = self.get_component("chat_panel")
            if chat_panel:
                await chat_panel.handle_message(message_data)
                return
        
        # If component_id is specified, route to that component directly
        if component_id and component_id in self.components:
            await self.components[component_id].handle_message(message_data)
            return
            
        # Otherwise use the message_type routing table
        if message_type in self.message_type_handlers:
            for component in self.message_type_handlers[message_type]:
                await component.handle_message(message_data)
        else:
            print(f"No component registered to handle message type: {message_type}")
            
    def get_component(self, component_id: str) -> Optional[Component]:
        """Get a component by ID"""
        return self.components.get(component_id)
            
    async def start_components(self):
        """Start all components that have a start method"""
        for component in self.components.values():
            if hasattr(component, 'start') and callable(component.start):
                await component.start()
                
    async def stop_components(self):
        """Stop all components that have a stop method"""
        for component in self.components.values():
            if hasattr(component, 'stop') and callable(component.stop):
                await component.stop() 