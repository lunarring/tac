import os
import yaml
import pytest
from src.tac.core.config import ConfigManager

@pytest.fixture(autouse=True)
def reset_config_manager():
    # Reset the singleton ConfigManager instance between tests.
    ConfigManager._instance = None
    yield
    ConfigManager._instance = None

def test_config_manager(tmp_path):
    # Prepare temporary YAML configuration file.
    config_data = {
        "general": {
            "type": "aider",
            "plausibility_test": True,
            "use_file_summaries": False
        },
        "git": {
            "enabled": True,
            "auto_commit_if_success": False
        },
        "llm_weak": {
            "provider": "openai",
            "model": "o1-mini",
            "settings": {
                "temperature": 0.5,
                "timeout": 120,
                "max_tokens": 150
            }
        }
    }
    config_file = tmp_path / "temp_config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(config_data, f)

    # Instantiate ConfigManager and reload from the temporary YAML file.
    cm = ConfigManager()
    cm.reload(str(config_file))

    # Verify 'general' configuration.
    general = cm.general
    assert general.type == "aider"
    assert general.plausibility_test is True
    assert general.use_file_summaries is False

    # Verify 'git' configuration.
    git = cm.git
    assert git.enabled is True
    assert git.auto_commit_if_success is False

    # Verify 'llm_weak' configuration.
    llm = cm.get_llm_config("weak")
    assert llm.model == "o1-mini"
    assert llm.provider == "openai"
    assert llm.settings.temperature == 0.5
    assert llm.settings.timeout == 120
    assert llm.settings.max_tokens == 150

    # Verify default value when key is missing.
    assert cm.get("nonexistent_key", "default") == "default"
