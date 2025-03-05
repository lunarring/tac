from pathlib import Path
import os
from typing import Any, Dict, Optional, List
from dataclasses import dataclass, field
import json
import argparse
from tac.core.log_config import setup_logging

# Initialize logger with default values - will be reconfigured later if needed
logger = setup_logging('tac.core.config', log_level='INFO', log_color='green')


@dataclass
class GitConfig:
    enabled: bool = True
    auto_commit_if_success: bool = True
    auto_push_if_success: bool = True


@dataclass
class GeneralConfig:
    agent_type: str = "native"
    reasoning_effort: str = "medium"
    use_orchestrator: bool = False
    plausibility_test: bool = True
    use_file_summaries: bool = True
    minimum_plausibility_score: str = "B"  # Minimum passing score for plausibility check (A, B, C, D, F)
    run_error_analysis: bool = True  # Whether to run error analysis after failures
    summarizer_timeout: int = 45  # Timeout in seconds for file summarization
    max_retries_block: int = 4
    max_retries_protoblock: int = 4
    total_timeout: int = 600
    halt_after_fail: bool = False
    ignore_paths: List[str] = field(default_factory=lambda: [".git", "__pycache__", "build"])
    test_path: str = "tests/"  # Add default test path
    save_protoblock: bool = False  # Whether to save protoblocks to disk
    default_trusty_agents: List[str] = field(default_factory=lambda: ["pytest", "plausibility"])  # Default trusty agents to use


@dataclass
class AiderConfig:
    model: str = "openai/o3-mini"
    reasoning_effort: str = "high"
    model_settings: Dict[str, Any] = field(default_factory=lambda: {
        "edit_format": "diff",
        "verify_ssl": True,
        "timeout": 240,
        "max_chat_history_tokens": 200000
    })


@dataclass
class LLMSettings:
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    verify_ssl: bool = True
    timeout: int = 120


@dataclass
class LLMConfig:
    provider: str = "openai"
    model: str = "o3-mini"
    settings: LLMSettings = field(default_factory=LLMSettings)
    api_key: Optional[str] = None
    base_url: Optional[str] = None


@dataclass
class LoggingConfig:
    tac: Dict[str, Any] = field(default_factory=lambda: {
        "level": "INFO",
        "color": "green"
    })
    other_packages: Dict[str, Any] = field(default_factory=lambda: {
        "level": "INFO"
    })

    def get_tac(self, key: str, default: Any = None) -> Any:
        """Get a value from tac config with a default."""
        return self.tac.get(key, default)

    def get_other_packages(self, key: str, default: Any = None) -> Any:
        """Get a value from other_packages config with a default."""
        return self.other_packages.get(key, default)


@dataclass
class Config:
    general: GeneralConfig = field(default_factory=GeneralConfig)
    git: GitConfig = field(default_factory=GitConfig)
    aider: AiderConfig = field(default_factory=AiderConfig)
    llm_strong: LLMConfig = field(default_factory=lambda: LLMConfig(
        provider="openai",
        model="o3-mini",
        settings=LLMSettings(
            temperature=0.7,
            max_tokens=None,
            verify_ssl=True,
            timeout=120
        )
    ))
    llm_weak: LLMConfig = field(default_factory=lambda: LLMConfig(
        provider="openai",
        model="o3-mini",
        settings=LLMSettings(
            temperature=0.7,
            max_tokens=None,
            verify_ssl=True,
            timeout=120
        )
    ))
    logging: LoggingConfig = field(default_factory=LoggingConfig)


class ConfigManager:
    _instance = None
    _config: Config = None
    _logger = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self) -> None:
        """Initialize the config manager with default values."""
        self._config = Config()
        # Update logging configuration
        self._setup_logger()

    def _setup_logger(self):
        """Setup logger for config manager - called after initial setup to avoid circular deps."""
        if self._logger is None:
            log_level = self._config.logging.get_tac('level', 'INFO')
            log_color = self._config.logging.get_tac('color', 'green')
            self._logger = setup_logging('tac.core.config', log_level=log_level, log_color=log_color)

    @property
    def raw_config(self) -> Dict[str, Any]:
        """Get the raw configuration dictionary."""
        return {
            'general': vars(self._config.general),
            'git': vars(self._config.git),
            'aider': vars(self._config.aider),
            'llm_strong': vars(self._config.llm_strong),
            'llm_weak': vars(self._config.llm_weak),
            'logging': vars(self._config.logging)
        }

    @property
    def git(self) -> GitConfig:
        """Get git configuration."""
        return self._config.git

    @property
    def general(self) -> GeneralConfig:
        """Get general configuration."""
        return self._config.general

    @property
    def aider(self) -> AiderConfig:
        """Get aider configuration."""
        return self._config.aider

    def get_llm_config(self, strength: str = "weak") -> LLMConfig:
        """Get LLM configuration for specified strength."""
        return getattr(self._config, f"llm_{strength}")

    @property
    def logging(self) -> LoggingConfig:
        """Get logging configuration."""
        return self._config.logging

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from config by key with a default."""
        return getattr(self._config, key, default)

    def override_with_args(self, args: dict) -> None:
        """Override configuration values with command-line arguments.
        
        Arguments with prefixes 'general_' or 'git_' update the corresponding nested dicts.
        Unprefixed arguments that match keys in general config are also applied to general config.
        Values that are None will not override the configuration.
        """
        self._setup_logger()  # Ensure logger is set up before using it
        
        if self._logger:  # Only log if logger is available
            self._logger.debug(f"Overriding config with args: {args}")
            self._logger.debug(f"Current general config before override: {vars(self._config.general)}")
        
        for key, value in args.items():
            if value is not None:
                if key.startswith("general_"):
                    subkey = key[len("general_"):]
                    if hasattr(self._config.general, subkey):
                        setattr(self._config.general, subkey, value)
                        if self._logger:
                            self._logger.debug(f"Set general config {subkey}={value} from prefixed arg")
                elif key.startswith("git_"):
                    subkey = key[len("git_"):]
                    if hasattr(self._config.git, subkey):
                        setattr(self._config.git, subkey, value)
                        if self._logger:
                            self._logger.debug(f"Set git config {subkey}={value} from prefixed arg")
                # Handle unprefixed arguments that match general config keys
                elif key.replace("-", "_") in vars(self._config.general):
                    normalized_key = key.replace("-", "_")
                    setattr(self._config.general, normalized_key, value)
                    if self._logger:
                        self._logger.debug(f"Set general config {normalized_key}={value} from unprefixed arg")
                elif hasattr(self._config, key):
                    setattr(self._config, key, value)
                    if self._logger:
                        self._logger.debug(f"Set root config {key}={value}")
        
        if self._logger:
            self._logger.debug(f"Final general config after override: {vars(self._config.general)}")

    def override_with_dict(self, config_dict: Dict[str, Dict[str, Any]]) -> None:
        """Override configuration values with a nested dictionary.
        
        The dictionary should have top-level keys matching config sections
        (general, git, aider, etc.) with nested dictionaries of settings.
        
        Example:
            {
                'general': {'plausibility_test': False},
                'git': {'auto_commit_if_success': False}
            }
        """
        self._setup_logger()

        if self._logger:
            self._logger.debug(f"Overriding config with dict: {config_dict}")

        for section, settings in config_dict.items():
            if hasattr(self._config, section):
                section_config = getattr(self._config, section)
                for key, value in settings.items():
                    if hasattr(section_config, key):
                        setattr(section_config, key, value)
                        if self._logger:
                            self._logger.debug(
                                f"Set {section} config {key}={value}"
                            )
                    else:
                        if self._logger:
                            self._logger.warning(
                                f"Unknown config key '{key}' in section '{section}'"
                            )
            else:
                if self._logger:
                    self._logger.warning(f"Unknown config section: {section}")


# Global instance
config = ConfigManager() 
