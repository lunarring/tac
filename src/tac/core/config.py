from pathlib import Path
import os
import yaml
from typing import Any, Dict, Optional
from dataclasses import dataclass, field
from functools import lru_cache


@dataclass
class GitConfig:
    enabled: bool = True
    auto_commit_if_success: bool = False


@dataclass
class GeneralConfig:
    type: str = "aider"
    plausibility_test: bool = False
    use_file_summaries: bool = False
    summarizer_timeout: int = 30
    max_retries: int = 3
    max_retries_protoblock_creation: int = 4
    halt_after_fail: bool = False


@dataclass
class LLMSettings:
    temperature: float = 0.7
    timeout: int = 120
    max_tokens: Optional[int] = None


@dataclass
class LLMConfig:
    provider: str = "deepseek"
    model: str = "deepseek-chat"
    settings: LLMSettings = field(default_factory=LLMSettings)
    api_key: Optional[str] = None
    base_url: Optional[str] = None


class ConfigManager:
    _instance = None
    _config: Dict[str, Any] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self) -> None:
        """Initialize the config manager by loading the config file."""
        self._config = self._load_config()

    @staticmethod
    def _get_default_config_path() -> Path:
        """Get the default config path."""
        return Path(__file__).parent.parent.parent.parent / 'config.yaml'

    @staticmethod
    @lru_cache()
    def _load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
        """Load configuration from yaml file with caching."""
        if config_path is None:
            config_path = ConfigManager._get_default_config_path()
        
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Could not find config file at: {config_path}")
        
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)

    def reload(self, config_path: Optional[str] = None) -> None:
        """Reload the configuration from file."""
        self._config = self._load_config(config_path)

    @property
    def raw_config(self) -> Dict[str, Any]:
        """Get the raw configuration dictionary."""
        return self._config

    @property
    def git(self) -> GitConfig:
        """Get git configuration."""
        git_config = self._config.get('git', {})
        return GitConfig(
            enabled=git_config.get('enabled', True),
            auto_commit_if_success=git_config.get('auto_commit_if_success', False)
        )

    @property
    def general(self) -> GeneralConfig:
        """Get general configuration."""
        general_config = self._config.get('general', {})
        return GeneralConfig(
            type=general_config.get('type', "aider"),
            plausibility_test=general_config.get('plausibility_test', False),
            use_file_summaries=general_config.get('use_file_summaries', False),
            summarizer_timeout=general_config.get('summarizer_timeout', 30),
            max_retries=general_config.get('max_retries', 3),
            max_retries_protoblock_creation=general_config.get('max_retries_protoblock_creation', 4),
            halt_after_fail=general_config.get('halt_after_fail', False)
        )

    def get_llm_config(self, strength: str = "weak") -> LLMConfig:
        """Get LLM configuration for specified strength."""
        config_key = f"llm_{strength}"
        llm_config = self._config.get(config_key, {})
        
        settings = llm_config.get('settings', {})
        llm_settings = LLMSettings(
            temperature=settings.get('temperature', 0.7),
            timeout=settings.get('timeout', 120),
            max_tokens=settings.get('max_tokens')
        )
        
        return LLMConfig(
            provider=llm_config.get('provider', 'deepseek'),
            model=llm_config.get('model', 'deepseek-chat'),
            settings=llm_settings,
            api_key=llm_config.get('api_key'),
            base_url=llm_config.get('base_url')
        )

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from config by key with a default."""
        return self._config.get(key, default)

    def override_with_args(self, args: dict) -> None:
        """Override configuration values with command-line arguments.
        
        Arguments with prefixes 'general_' or 'git_' update the corresponding nested dicts.
        Unprefixed arguments that match keys in general config are also applied to general config.
        Values that are None will not override the configuration.
        """
        for key, value in args.items():
            if value is not None:
                if key.startswith("general_"):
                    subkey = key[len("general_"):]
                    self._config.setdefault("general", {})[subkey] = value
                elif key.startswith("git_"):
                    subkey = key[len("git_"):]
                    self._config.setdefault("git", {})[subkey] = value
                # Handle unprefixed arguments that match general config keys
                elif key.replace("-", "_") in vars(self.general):
                    self._config.setdefault("general", {})[key.replace("-", "_")] = value
                else:
                    self._config[key] = value


# Global instance
config = ConfigManager() 
