import asyncio
import json
import pytest
from tac.web.ui import UIManager

class DummyWebSocket:
    def __init__(self):
        self.sent = []

    async def send(self, message):
        self.sent.append(message)

@pytest.mark.asyncio
async def test_settings_button_click():
    ui_manager = UIManager()
    dummy_ws = DummyWebSocket()
    # Simulate the settings button click event
    await ui_manager.handle_settings_click(dummy_ws)
    # Ensure a message was sent through the websocket
    assert len(dummy_ws.sent) == 1
    # The sent message should be a JSON string with type "settings_page"
    message_data = json.loads(dummy_ws.sent[0])
    assert message_data.get("type") == "settings_page"
    html_content = message_data.get("html")
    # Check that key configuration elements are present in the HTML
    assert "Component LLM Mappings" in html_content, "Expected 'Component LLM Mappings' in settings HTML"
    assert "llm-selector" in html_content, "Expected 'llm-selector' in settings HTML"
    
if __name__ == "__main__":
    pytest.main([__file__])