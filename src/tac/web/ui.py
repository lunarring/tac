import asyncio
import json
import websockets
import socket
import os
import signal
import subprocess
import argparse
from tac.agents.misc.chat import ChatAgent
from tac.utils.project_files import ProjectFiles
from tac.utils.audio import Speech2Text  # Newly imported for speech-to-text functionality
from tac.cli.main import execute_command
from tac.core.llm import LLMClient, Message

# Global variables to manage recording state and speech-to-text instance
is_recording = False
speech_to_text = Speech2Text()

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

async def dummy_mic_click(websocket):
    global is_recording, speech_to_text
    # On first button press, start recording. On the next press, stop recording.
    if not is_recording:
        speech_to_text.start_recording()
        print("Recording started.")
        is_recording = True
    else:
        transcript = speech_to_text.stop_recording()
        print("Recording stopped. Transcript:", transcript)
        is_recording = False
        if transcript:
            # Send transcript to client as a user message
            # The client should display this as a user message in the UI
            payload = {
                "type": "transcribed_message", 
                "message": transcript
            }
            await websocket.send(json.dumps(payload))

async def handle_connection(websocket):
    # Retrieve high-level file summaries from the project
    file_summaries = load_high_level_summaries()
    # Incorporate the file summaries into the system prompt for broader context
    system_content = ("You are a senior coding god. You are replying a bit sassy and sarcastic. You are also a bit of a know it all.  A high level summary of the codebase which the user wants to modify is here: {file_summaries}. Always reply concise and without formatting. Your task is to ask questions and clarify requests, for this early phase of software design. Always try to be brief and concise and help the planning. Remember, the user is not the one who is implementing the code, it is actually you and your team of AI agents and they use trusty agents to verify the code. So don't tell the user how to do it themselves, but rather try to gather information about what the user wants to build in the context of the codebase above. Don't be too verbose about the code itself, but rather gather an understanding of what the user really wants. Always be brief and to the point! However the goal is to end up with ONE clear task and do them one at a time.")
    formatted_system_content = system_content.format(file_summaries=file_summaries)
    # Initialize ChatAgent with the new system prompt that includes file summaries.
    agent = ChatAgent(system_prompt=formatted_system_content)

    while True:
        try:
            user_input_raw = await websocket.recv()
            print("Received message from client:", user_input_raw)
            user_message = None
            
            # Try to parse the incoming message as JSON
            try:
                data = json.loads(user_input_raw)
                if isinstance(data, dict) and "type" in data:
                    message_type = data["type"]
                    
                    if message_type == "mic_click":
                        await dummy_mic_click(websocket)
                        continue
                    elif message_type == "block_click":
                        # Handle block click event - compress chat and generate protoblock
                        await handle_block_click(websocket, agent)
                        continue
                    elif message_type in ["user_message", "transcribed_message"]:
                        user_message = data.get("message", "").strip()
                else:
                    # JSON but not our expected format
                    user_message = user_input_raw.strip()
            except json.JSONDecodeError:
                # Not JSON, handle as plain text for backward compatibility
                if user_input_raw.strip() == "mic_click":
                    await dummy_mic_click(websocket)
                    continue
                user_message = user_input_raw.strip()

            if user_message:
                # Process the incoming user message
                assistant_reply = agent.process_message(user_message)
                print(f"Sending message to client: {assistant_reply}")
                await websocket.send(assistant_reply)
        except websockets.exceptions.ConnectionClosed:
            break
        except Exception as e:
            print(f"Error in processing message: {e}")
            break

async def handle_block_click(websocket, agent):
    """
    Handle the block button click by:
    1. Generating task instructions from the conversation
    2. Creating config overrides
    3. Running the execute_command function
    """
    try:
        # Send status message to client
        await websocket.send(json.dumps({
            "type": "status_message",
            "message": "Creating block from conversation..."
        }))
        
        # Generate task instructions from the chat history
        genesis_prompt = agent.generate_task_instructions()
        
        # Prepare config overrides for execute_command
        config_overrides = {
            'no_git': False,
            'json': None,
            'image': None
        }
        
        # For any LLM-specific config
        for attr in ['llm_type', 'model', 'api_base', 'json_mode']:
            config_overrides[attr] = None
        
        # Inform client that execution is starting
        await websocket.send(json.dumps({
            "type": "status_message",
            "message": "Executing block with instructions: " + genesis_prompt[:100] + "..."
        }))
        
        # Run execution in a separate thread to not block the websocket
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(None, lambda: execute_command(
            task_instructions=genesis_prompt,
            config_overrides=config_overrides
        ))
        
        # Report result back to client
        if success:
            await websocket.send(json.dumps({
                "type": "status_message",
                "message": "✅ Block executed successfully!"
            }))
        else:
            await websocket.send(json.dumps({
                "type": "status_message",
                "message": "❌ Block execution failed."
            }))
    
    except Exception as e:
        print(f"Error during block execution: {e}")
        import traceback
        traceback.print_exc()
        await websocket.send(json.dumps({
            "type": "status_message",
            "message": f"❌ Error: {str(e)}"
        }))

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
        