import pytest
from tac.agents.misc.chat import ChatAgent

def test_single_message_default():
    agent = ChatAgent()
    response = agent.process_message("Hello")
    expected = "You are a helpful assistant. Hello"
    assert response == expected, f"Expected '{expected}' but got '{response}'"

def test_multiple_messages_default():
    agent = ChatAgent()
    # First message.
    response1 = agent.process_message("Hello")
    expected1 = "You are a helpful assistant. Hello"
    assert response1 == expected1, f"Expected '{expected1}' but got '{response1}'"
    # Second message.
    response2 = agent.process_message("World")
    expected2 = "You are a helpful assistant. Hello World"
    assert response2 == expected2, f"Expected '{expected2}' but got '{response2}'"

def test_custom_system_prompt():
    agent = ChatAgent(system_prompt="System")
    response = agent.process_message("Hello")
    expected = "System Hello"
    assert response == expected, f"Expected '{expected}' but got '{response}'"

def test_conversation_state_length():
    agent = ChatAgent(system_prompt="Sys")
    agent.process_message("Hi")
    # Conversation should have 3 entries: system, user, and assistant.
    assert len(agent.conversation) == 3, f"Expected conversation length 3 but got {len(agent.conversation)}"