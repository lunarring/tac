import pytest
from src.tac.core.llm import LLMClient, Message
from src.tac.core.config import LLMConfig, LLMSettings

class DummyMessage:
    def __init__(self):
        self.content = "Success response"

class DummyChoice:
    def __init__(self):
        self.message = DummyMessage()

class DummySuccessResponse:
    def __init__(self):
        self.choices = [DummyChoice()]

def dummy_success(*args, **kwargs):
    return DummySuccessResponse()

def test_llm_success(monkeypatch):
    config_override = {
        "provider": "openai",
        "model": "o1-mini",
        "settings": LLMSettings(timeout=120)
    }
    client = LLMClient(config_override=config_override)
    
    monkeypatch.setattr(client.client.chat.completions, "create", dummy_success)
    
    messages = [Message(role="user", content="Test message")]
    result = client.chat_completion(messages)
    assert result == "Success response"
