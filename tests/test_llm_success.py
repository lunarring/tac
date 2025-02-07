import pytest
from src.tac.core.llm import LLMClient, Message, LLMConfig

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
    config = LLMConfig(provider="openai", model="o1-mini", settings={"timeout": 120})
    client = LLMClient(config=config)
    
    monkeypatch.setattr(client.client.chat.completions, "create", dummy_success)
    
    messages = [Message(role="user", content="Test message")]
    result = client.chat_completion(messages)
    assert result == "Success response"
