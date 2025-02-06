import pytest
from src.tac.core.llm import LLMClient, Message, LLMConfig

def dummy_failure(*args, **kwargs):
    raise Exception("Simulated API failure")

def test_llm_failure(monkeypatch):
    # Setup a dummy config and instantiate the LLM client
    config = LLMConfig(provider="openai", model="o1-mini", settings={"timeout": 120})
    client = LLMClient(config=config)
    
    # Monkey-patch the chat completions create method to simulate failure
    monkeypatch.setattr(client.client.chat.completions, "create", dummy_failure)
    
    messages = [Message(role="user", content="Test message")]
    result = client.chat_completion(messages)
    assert "LLM failure" in result
