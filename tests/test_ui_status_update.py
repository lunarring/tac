import asyncio
import pytest
from tac.web.ui import UIManager

# Define dummy async functions to override real implementations during testing
async def dummy_send_status(message):
    return

async def dummy_send_recording_status(status):
    return

class DummyServer:
    async def send_status_message(self, message):
        # For testing, we do nothing (status is captured via ui_manager.latest_status)
        return

@pytest.mark.asyncio
async def test_mic_release_updates_status():
    ui_manager = UIManager(base_dir=".")
    # Override the server with a dummy server to avoid real websocket operations.
    ui_manager.server = DummyServer()
    # Override send_status_message to capture the latest status (already handled in UIManager.send_status_message)
    # Override speech_input.send_recording_status with dummy async function
    ui_manager.speech_input.send_recording_status = dummy_send_recording_status
    # Patch stop_recording to simulate a dummy transcription result.
    ui_manager.speech_to_text.stop_recording = lambda: "dummy transcription"
    
    # Set initial state to recording (simulate that recording was active)
    ui_manager.is_recording = True
    # Simulate mic release event by sending {'recording': False}
    await ui_manager.message_handler.handle_mic_click({'recording': False})
    
    # Check that the latest status message is updated to "Waiting for input" after transcription completes.
    assert ui_manager.latest_status == "Waiting for input"