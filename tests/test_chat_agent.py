import asyncio
import json
import pytest
import websockets

from tac.agents.misc import chat
from tac.core.llm import Message

# Fake LLMClient to simulate predictable responses for testing
class FakeLLMClient:
    def __init__(self, llm_type):
        self.llm_type = llm_type
    def chat_completion(self, conversation):
        # Find the most recent user message in the conversation
        user_message = ""
        for msg in conversation:
            if msg.role == "user":
                user_message = msg.content
        response = {"content": f"Echo: {user_message}"}
        return json.dumps(response)

# Fake WebSocket to simulate a client connection
class FakeWebSocket:
    def __init__(self, messages):
        self.messages = messages  # List of messages to be sent by the client
        self.sent_msgs = []       # Captured messages that are sent to the client
    async def recv(self):
        if self.messages:
            return self.messages.pop(0)
        else:
            # Simulate connection closure when no messages remain
            raise websockets.exceptions.ConnectionClosed(1000, "Closed")
    async def send(self, message):
        self.sent_msgs.append(message)

@pytest.mark.asyncio
async def test_handle_connection():
    # Monkey-patch LLMClient in the chat module with our fake implementation
    original_llm_client = chat.LLMClient
    chat.LLMClient = FakeLLMClient

    # Create a fake websocket with an initial test message
    fake_ws = FakeWebSocket(["test message"])
    agent = chat.ChatAgent()
    # Execute the handle_connection method which will process the simulated message
    await agent.handle_connection(fake_ws)

    # Verify that the chat agent responded with the expected echo response
    assert len(fake_ws.sent_msgs) == 1
    assert fake_ws.sent_msgs[0] == "Echo: test message"

    # Restore the original LLMClient
    chat.LLMClient = original_llm_client