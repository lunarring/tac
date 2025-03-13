import pytest
from tac.coding_agents.constructor import CodingAgentConstructor
from tac.coding_agents.aider import AiderAgent
from tac.coding_agents.native_agent import NativeAgent

def test_create_aider_agent():
    # Set a dummy configuration override to simulate aide agent selection
    dummy_config_override = {"general": {"coding_agent": "aider"}}
    agent = CodingAgentConstructor.create_agent("aider", dummy_config_override)
    assert isinstance(agent, AiderAgent)

def test_create_native_agent():
    # Set a dummy configuration override to simulate native agent selection
    dummy_config_override = {"general": {"coding_agent": "native"}}
    agent = CodingAgentConstructor.create_agent("native", dummy_config_override)
    assert isinstance(agent, NativeAgent)

def test_invalid_agent_type():
    # Providing an invalid agent type should raise a ValueError
    dummy_config_override = {"general": {"coding_agent": "invalid_agent"}}
    with pytest.raises(ValueError):
        CodingAgentConstructor.create_agent("invalid_agent", dummy_config_override)
        