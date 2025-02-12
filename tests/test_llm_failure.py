import pytest
from src.tac.core.llm import LLMClient, Message
from src.tac.core.config import LLMConfig, LLMSettings

def dummy_failure(*args, **kwargs):
    raise Exception("Simulated API failure")

def test_llm_failure(monkeypatch):
    # Setup a dummy config and instantiate the LLM client
    config_override = {
        "provider": "openai",
        "model": "o1-mini",
        "settings": LLMSettings(timeout=120)
    }
    client = LLMClient(config_override=config_override)
    
    # Monkey-patch the chat completions create method to simulate failure
    monkeypatch.setattr(client.client.chat.completions, "create", dummy_failure)
    
    messages = [Message(role="user", content="Test message")]
    result = client.chat_completion(messages)
    assert "LLM failure" in result
