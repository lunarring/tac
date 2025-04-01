import asyncio
import pytest
from tac.web import ui

class DummyWebSocket:
    def __init__(self):
        self.sent_messages = []

    async def send(self, message):
        self.sent_messages.append(message)

@pytest.mark.asyncio
async def test_handle_block_click():
    dummy_ws = DummyWebSocket()
    # Pass a dummy agent since it is not used in the block click handler.
    await ui.handle_block_click(dummy_ws, None)
    assert dummy_ws.sent_messages[0] == "making block..."