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
            use_file_summaries=False,
            summarizer_timeout=30,
            max_retries_block_creation=3,
            max_retries_protoblock_creation=4,
            halt_after_fail=False,
            default_trusty_agents=["pytest"]
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
    assert cm.general.default_trusty_agents == ["pytest"]
    assert cm.general.use_file_summaries is False
    assert cm.general.summarizer_timeout == 30
    assert cm.general.max_retries_block_creation == 3
    assert cm.general.max_retries_protoblock_creation == 4
    assert cm.general.halt_after_fail is False
    assert cm.git.auto_commit_if_success is False

def test_override_with_dict():
    cm = ConfigManager()
    
    config_dict = {
        'general': {
            'agent_type': 'custom',
            'max_retries_block_creation': 3,
            'run_error_analysis': False
        },
        'git': {
            'enabled': False
        }
    }
    
    cm.override_with_dict(config_dict)
    
    # Verify overrides were applied
    assert cm.general.agent_type == 'custom'
    assert cm.general.max_retries_block_creation == 3
    assert cm.general.run_error_analysis is False
    assert cm.git.enabled is False
