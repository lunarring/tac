import os
import pytest
from tac.core.llm import LLMClient, Message

# A dummy response class to simulate API response for testing
class DummyMessage:
    def __init__(self, content):
        self.content = content

class DummyChoice:
    def __init__(self, content):
        self.message = DummyMessage(content)

class DummyResponse:
    def __init__(self, params):
        # Return the parameters as the dummy response content for inspection.
        self.choices = [DummyChoice(params)]

# Dummy client to intercept API call and return a dummy response
class DummyChatCompletions:
    def __init__(self, captured):
        self.captured = captured

    def create(self, **params):
        self.captured.clear()
        self.captured.update(params)
        return DummyResponse(params)

class DummyChat:
    def __init__(self, captured):
        self.completions = DummyChatCompletions(captured)

class DummyAPIClient:
    def __init__(self, captured):
        self.chat = DummyChat(captured)

def override_client(client_instance, captured):
    client_instance.client = DummyAPIClient(captured)

def test_chat_completion_supported_model():
    # Supported model: o3-mini should include reasoning_effort
    client = LLMClient(llm_type="weak")
    client.config.model = "o3-mini"
    client.config.settings.reasoning_effort = "high"
    captured_params = {}
    override_client(client, captured_params)
    messages = [Message(role="user", content="Hello, supported model.")]
    _ = client.chat_completion(messages)
    assert "reasoning_effort" in captured_params
    assert captured_params["reasoning_effort"] == "high"

def test_chat_completion_unsupported_model():
    # Unsupported model: gpt-4o should not include reasoning_effort
    client = LLMClient(llm_type="weak")
    client.config.model = "gpt-4o"
    client.config.settings.reasoning_effort = "medium"
    captured_params = {}
    override_client(client, captured_params)
    messages = [Message(role="user", content="Hello, unsupported model.")]
    _ = client.chat_completion(messages)
    assert "reasoning_effort" not in captured_params

def test_vision_chat_completion_supported_model():
    # For vision completion with supported model, reasoning_effort should be included.
    client = LLMClient(llm_type="vision")
    client.config.model = "o3-mini"
    client.config.settings.reasoning_effort = "medium"
    captured_params = {}
    override_client(client, captured_params)
    # Create a dummy image file for testing
    test_image_path = "test_image.png"
    from PIL import Image
    img = Image.new("RGB", (100, 100), color="red")
    img.save(test_image_path)
    
    messages = [Message(role="user", content="Vision test with supported model.")]
    _ = client.vision_chat_completion(messages, test_image_path)
    os.remove(test_image_path)
    assert "reasoning_effort" in captured_params
    assert captured_params["reasoning_effort"] == "medium"

def test_vision_chat_completion_unsupported_model():
    # For vision completion with unsupported model, reasoning_effort should not be included.
    client = LLMClient(llm_type="vision")
    client.config.model = "gpt-4o"
    client.config.settings.reasoning_effort = "medium"
    captured_params = {}
    override_client(client, captured_params)
    # Create a dummy image file for testing
    test_image_path = "test_image.png"
    from PIL import Image
    img = Image.new("RGB", (100, 100), color="blue")
    img.save(test_image_path)
    
    messages = [Message(role="user", content="Vision test with unsupported model.")]
    _ = client.vision_chat_completion(messages, test_image_path)
    os.remove(test_image_path)
    assert "reasoning_effort" not in captured_params