import asyncio
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

    # Assert that 3 messages were received and each is a random 10-character string.
    assert len(messages) == 3
    for msg in messages:
        assert isinstance(msg, str)
        assert len(msg) == 10