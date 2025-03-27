import asyncio
import json
import random
import string
import pytest
import websockets
from tac.web.ui import run_server

@pytest.mark.asyncio
async def test_websocket_server():
    # Start the websocket server in the background
    server_task = asyncio.create_task(run_server())
    await asyncio.sleep(0.5)  # Give the server time to start

    messages = []
    try:
        async with websockets.connect("ws://localhost:8765") as websocket:
            # Receive 3 messages from the server
            for _ in range(3):
                msg = await websocket.recv()
                messages.append(msg)
    finally:
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass

    # Assert that 3 messages were received and each is a JSON object with 'type' and 'content' keys.
    # The 'content' field should be a random 10-character string.
    assert len(messages) == 3
    for raw_msg in messages:
        assert isinstance(raw_msg, str)
        try:
            msg = json.loads(raw_msg)
        except Exception as e:
            assert False, f"Failed to parse JSON: {e}"

        assert isinstance(msg, dict)
        assert 'type' in msg
        assert 'content' in msg
        assert isinstance(msg['content'], str)
        assert len(msg['content']) == 10