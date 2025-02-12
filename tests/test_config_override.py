import pytest
from argparse import Namespace
from src.tac.core.config import ConfigManager

def test_override_with_args():
    # Create a new ConfigManager instance and override its internal _config for testing.
    cm = ConfigManager()
    cm._config = {
        "general": {
            "type": "aider",
            "plausibility_test": False,
            "use_file_summaries": False,
            "summarizer_timeout": 30,
            "max_retries": 3,
            "max_retries_protoblock_creation": 4,
            "halt_after_fail": False
        },
        "git": {
            "enabled": True,
            "auto_commit_if_success": False
        },
    }
    # Create dummy CLI arguments; note that other_arg should not affect the configuration.
    args = Namespace(general_type="new_aider", git_enabled=False, other_arg=None)
    cm.override_with_args(vars(args))
    
    # Assert that the configuration values have been overridden.
    assert cm.general.type == "new_aider"
    assert cm.git.enabled is False
