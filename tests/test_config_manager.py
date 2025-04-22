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
    assert general.coding_agent in ["aider", "native"]
    # default_trusty_agents has been completely removed
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


    # Verify default value when key is missing
    assert cm.get("nonexistent_key", "default") == "default"


def test_raw_config():
    cm = ConfigManager()
    raw = cm.raw_config
    
    assert isinstance(raw, dict)
    assert 'general' in raw
    assert 'git' in raw
    assert raw['general']['coding_agent'] in ['aider', 'native']
    # llm_strong and llm_weak keys are no longer in config
    assert 'logging' in raw
