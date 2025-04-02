import asyncio
import json
import os
import pytest
from bs4 import BeautifulSoup
from tac.web.ui import UIManager
import websockets

class DummyWebSocket:
    def __init__(self, recv_messages):
        # List of messages that recv() will return.
        self.recv_messages = recv_messages
        self.sent_messages = []

    async def recv(self):
        if self.recv_messages:
            return self.recv_messages.pop(0)
        else:
            # Simulate connection closed after messages are exhausted.
            raise websockets.exceptions.ConnectionClosed(1000, "closed")

    async def send(self, message):
        self.sent_messages.append(message)

@pytest.mark.asyncio
async def test_runtime_status_update_message_updates_status_bar():
    # Prepare a dummy websocket with a runtime_status_update message from client.
    test_status = "updated status"
    incoming_message = json.dumps({
        "type": "runtime_status_update",
        "message": test_status
    })
    dummy_ws = DummyWebSocket(recv_messages=[incoming_message])

    ui_manager = UIManager()
    # Run handle_connection; it will process one message and then hit connection closed.
    await ui_manager.handle_connection(dummy_ws)

    # Now, verify that the websocket sent back a runtime_status_update message.
    assert dummy_ws.sent_messages, "No messages were sent by UIManager."
    # Look for a message with type runtime_status_update.
    sent_payload = None
    for msg in dummy_ws.sent_messages:
        try:
            data = json.loads(msg)
            if data.get("type") == "runtime_status_update":
                sent_payload = data
                break
        except Exception:
            continue
    assert sent_payload is not None, "UIManager did not send a runtime_status_update payload."
    assert sent_payload.get("message") == test_status, f"Expected status '{test_status}', but got '{sent_payload.get('message')}'."

    # Simulate client-side DOM update by loading index.html and updating the runtimeStatus element.
    html_path = os.path.join(os.path.dirname(__file__), "..", "src", "tac", "web", "index.html")
    assert os.path.exists(html_path), "index.html file does not exist at expected location."
    with open(html_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")
    runtime_status_element = soup.find(id="runtimeStatus")
    assert runtime_status_element is not None, "Runtime status element not found in index.html."
    # Simulate the client JavaScript updating the element's text.
    runtime_status_element.string = sent_payload.get("message")
    assert runtime_status_element.get_text(strip=True) == test_status, (
        f"Runtime status element text expected to be '{test_status}' but was '{runtime_status_element.get_text(strip=True)}'."
    )

if __name__ == "__main__":
    pytest.main()