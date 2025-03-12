import pytest
from src.tac.core.llm import LLMClient, Message
from src.tac.core.config import LLMSettings

def dummy_unknown_param_failure(*args, **kwargs):
    raise Exception('Unknown parameter: "reasoning_effort".')

def test_reasoning_effort_error(monkeypatch):
    config_override = {
        "provider": "openai",
        "model": "o1-mini",
        "settings": LLMSettings(timeout=120)
    }
    client = LLMClient(config_override=config_override)
    monkeypatch.setattr(client.client.chat.completions, "create", dummy_unknown_param_failure)
    messages = [Message(role="user", content="Test message")]
    result = client.chat_completion(messages)
    assert 'Unknown parameter: "reasoning_effort".' in result