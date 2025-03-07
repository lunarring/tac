import pytest
from src.tac.core.config import ConfigManager, Config, GeneralConfig, GitConfig, LLMConfig, LLMSettings

@pytest.fixture(autouse=True)
def reset_config_manager():
    # Reset the singleton ConfigManager instance between tests.
    ConfigManager._instance = None
    yield
    ConfigManager._instance = None

def test_config_manager():
    # Instantiate ConfigManager with default values
    cm = ConfigManager()

    # Verify 'general' configuration
    general = cm.general
    assert general.agent_type in ["aider", "native"]
    assert "pytest" in general.default_trusty_agents
    assert "plausibility" in general.default_trusty_agents
    assert general.use_file_summaries is True
    assert general.summarizer_timeout == 45
    assert general.max_retries_block_creation == 4
    assert general.max_retries_protoblock_creation == 4
    assert general.total_timeout == 600
    assert general.halt_after_fail is False

    # Verify 'git' configuration
    git = cm.git
    assert git.enabled is True
    assert git.auto_commit_if_success is True

    # Verify 'llm_weak' configuration
    llm = cm.get_llm_config("weak")
    assert llm.model == "o3-mini"
    assert llm.provider == "openai"
    assert llm.settings.temperature == 0.7
    assert llm.settings.timeout == 120
    assert llm.settings.max_tokens is None
    assert llm.settings.verify_ssl is True

    # Verify default value when key is missing
    assert cm.get("nonexistent_key", "default") == "default"

def test_config_override():
    cm = ConfigManager()
    
    # Test overriding general config
    cm.override_with_args({
        "general_agent_type": "claude",
        "general_reasoning_effort": "high",
        "general_max_retries_block_creation": 10,
        "general_default_trusty_agents": ["pytest"],  # Test overriding trusty agents
        "nonexistent_key": "value"  # This should be ignored
    })
    
    assert cm.general.agent_type == "claude"
    assert cm.general.reasoning_effort == "high"
    assert cm.general.max_retries_block_creation == 10
    assert cm.general.default_trusty_agents == ["pytest"]
    
    # Test overriding git config
    cm.override_with_args({
        "git_enabled": False,
        "git_auto_commit_if_success": False
    })
    
    assert cm.git.enabled is False
    assert cm.git.auto_commit_if_success is False

def test_raw_config():
    cm = ConfigManager()
    raw = cm.raw_config
    
    assert isinstance(raw, dict)
    assert 'general' in raw
    assert 'git' in raw
    assert raw['general']['agent_type'] in ['aider', 'native']
    assert 'llm_strong' in raw
    assert 'llm_weak' in raw
    assert 'logging' in raw
