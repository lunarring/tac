import pytest
from argparse import Namespace
from src.tac.core.config import ConfigManager, Config, GeneralConfig, GitConfig

def test_override_with_args():
    # Create a new ConfigManager instance
    cm = ConfigManager()
    
    # Create a Config instance with test values
    cm._config = Config(
        general=GeneralConfig(
            agent_type="aider",
            plausibility_test=False,
            use_file_summaries=False,
            summarizer_timeout=30,
            max_retries_block=3,
            max_retries_protoblock=4,
            halt_after_fail=False
        ),
        git=GitConfig(
            enabled=True,
            auto_commit_if_success=False
        )
    )

    # Create dummy CLI arguments; note that other_arg should not affect the configuration
    args = Namespace(general_agent_type="new_aider", git_enabled=False, other_arg=None)
    
    # Test the override
    cm.override_with_args(vars(args))
    
    # Verify the changes
    assert cm.general.agent_type == "new_aider"
    assert cm.git.enabled is False
    # Verify unchanged values
    assert cm.general.plausibility_test is False
    assert cm.general.use_file_summaries is False
    assert cm.general.summarizer_timeout == 30
    assert cm.general.max_retries_block == 3
    assert cm.general.max_retries_protoblock == 4
    assert cm.general.halt_after_fail is False
    assert cm.git.auto_commit_if_success is False
