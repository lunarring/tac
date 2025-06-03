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
class TrustyAgentConfig:
    # Plausibility agent settings
    minimum_plausibility_score: str = "C"  # Minimum passing score (A, B, C, D, F)
    
    # ThreeJS Vision agent settings
    minimum_vision_score: str = "C"  # Minimum passing score (A, B, C, D, F)
    vision_timeout: int = 15  # Timeout in seconds for vision agent program execution
    vision_screenshot_delay: int = 5  # Delay in seconds before taking a screenshot
    
    # Pytest agent settings
    run_error_analysis: bool = True  # Whether to run error analysis after failures
    exclude_performance_tests: bool = True  # Whether to exclude performance and transient tests
    
    # General trusty agent settings
    run_all_trusty_agents: bool = True  # Whether to run all selected trusty agents, even after failures


@dataclass
class GeneralConfig:
    coding_agent: str = "native"
    use_file_summaries: bool = True
    trusty_agents: TrustyAgentConfig = field(default_factory=TrustyAgentConfig)
    summarizer_timeout: int = 45  # Timeout in seconds for file summarization
    max_retries_block_creation: int = 4
    max_retries_protoblock_creation: int = 4
    total_timeout: int = 600
    halt_after_fail: bool = False
    halt_after_verify: bool = False  # Whether to pause for manual review after successful verification
    ignore_paths: List[str] = field(default_factory=lambda: [".git", "__pycache__", "build"])
    test_path: str = "tests/"  # Add default test path
    save_protoblock: bool = False  # Whether to save protoblocks to disk
    use_orchestrator: bool = False
    confirm_multiblock_execution: bool = False  # Whether to ask for confirmation before executing multiblock chunks
    # File peeker settings
    file_peeker_summary_level: str = "detailed"  # Options: "high_level", "detailed", "auto"
    file_peeker_max_files: int = 10  # Maximum number of files to include in context


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
    timeout: int = 240
    max_image_dimension: int = 1200  # Maximum dimension for image downscaling
    reasoning_effort: str = "medium"  # Added reasoning_effort


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
    
    # Template-based LLM configurations
    llm_templates: Dict[str, LLMConfig] = field(default_factory=lambda: {
        # Default templates based on actual model names
        "gpt-4o": LLMConfig(
            provider="openai",
            model="gpt-4o",
            settings=LLMSettings(
                temperature=0.7,
                max_tokens=16000,
                verify_ssl=True,
                timeout=180,
                reasoning_effort="medium"
            )
        ),
        "gpt-4o-2024-08-06": LLMConfig(
            provider="openai",
            model="gpt-4o-2024-08-06",
            settings=LLMSettings(
                temperature=0.7,
                max_tokens=4096,
                verify_ssl=True,
                timeout=120,
                reasoning_effort="low"
            )
        ),
        "o3-mini": LLMConfig(
            provider="openai",
            model="o3-mini",
            settings=LLMSettings(
                temperature=0.7,
                max_tokens=50000,
                verify_ssl=True,
                timeout=120,
                reasoning_effort="medium"
            )
        ),        
        "o4-mini": LLMConfig(
            provider="openai",
            model="o4-mini",
            settings=LLMSettings(
                temperature=0.7,
                max_tokens=50000,
                verify_ssl=True,
                timeout=120,
                reasoning_effort="medium"
            )
        ),
        "deepseek-reasoner": LLMConfig(
            provider="deepseek",
            model="deepseek-reasoner",
            settings=LLMSettings(
                temperature=0.7,
                max_tokens=None,
                verify_ssl=True,
                timeout=120,
                reasoning_effort="high"
            )
        ),
        "gemini-1.5-pro": LLMConfig(
            provider="gemini",
            model="gemini-1.5-pro",
            settings=LLMSettings(
                temperature=0.7,
                max_tokens=2048,
                verify_ssl=True,
                timeout=120,
                reasoning_effort="medium"
            )
        ),
        "gemini-2.5-pro": LLMConfig(
            provider="gemini",
            model="gemini-2.5-pro",
            settings=LLMSettings(
                temperature=0.7,
                max_tokens=8192,
                verify_ssl=True,
                timeout=120,
                reasoning_effort="high"
            )
        )
    })
    
    # Component-to-template mappings
    component_llm_mappings: Dict[str, str] = field(default_factory=lambda: {
        # Specify which template to use for each component
        "native_agent": "o3-mini",
        "protoblock_generation": "o3-mini",
        "chat": "gpt-4o-2024-08-06",
        "file_summarizer": "gpt-4o-2024-08-06",
        "file_peeker": "gpt-4o-2024-08-06",
        "orchestrator": "o3-mini",
        "vision": "gpt-4o",  # Vision model needs to be gpt-4o
        "code_reviewer": "o3-mini",  # Code reviewer testing uses o4-mini
        "default": "o3-mini"  # Default template when component not specified
    })
    
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
        # Load user config if it exists
        self.load_config()
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
            'llm_templates': {k: vars(v) for k, v in self._config.llm_templates.items()},
            'component_llm_mappings': self._config.component_llm_mappings,
            'logging': vars(self._config.logging)
        }

    def save_config_to_file(self) -> bool:
        """Save the current configuration to a JSON file in the user's home directory."""
        config_dir = Path.home() / ".tac"
        config_dir.mkdir(exist_ok=True)
        config_file = config_dir / "config.json"
        
        # Convert the dataclass structure to a serializable dictionary
        config_dict = {
            'general': vars(self._config.general),
            'git': vars(self._config.git),
            'aider': vars(self._config.aider),
            'llm_templates': {k: {
                'provider': v.provider,
                'model': v.model,
                'settings': vars(v.settings) if v.settings else {},
                'api_key': v.api_key,
                'base_url': v.base_url
            } for k, v in self._config.llm_templates.items()},
            'component_llm_mappings': self._config.component_llm_mappings,
            'logging': vars(self._config.logging)
        }
        
        # Handle nested dataclasses
        general_trusty_agents = config_dict['general'].pop('trusty_agents', None)
        if general_trusty_agents:
            config_dict['general']['trusty_agents'] = vars(general_trusty_agents)
        
        # Write to file
        try:
            with open(config_file, 'w') as f:
                json.dump(config_dict, f, indent=2)
            if self._logger:
                self._logger.info(f"Configuration saved to {config_file}")
            return True
        except Exception as e:
            if self._logger:
                self._logger.error(f"Error saving configuration: {e}")
            return False

    def load_config(self) -> None:
        """Load configuration from a JSON file in the user's home directory."""
        config_dir = Path.home() / ".tac"
        config_file = config_dir / "config.json"
        
        # Create the config directory if it doesn't exist
        config_dir.mkdir(exist_ok=True)
        
        if not config_file.exists():
            if self._logger:
                self._logger.debug(f"No config file found at {config_file}, using defaults")
            return
        
        try:
            with open(config_file, 'r') as f:
                config_dict = json.load(f)
                
            if self._logger:
                self._logger.debug(f"Loaded config from {config_file}: {config_dict.keys()}")
                if 'component_llm_mappings' in config_dict:
                    self._logger.debug(f"Found component_llm_mappings: {config_dict['component_llm_mappings']}")
            
            # Update the config with the loaded values
            for section, settings in config_dict.items():
                if hasattr(self._config, section):
                    # Handle special case for component_llm_mappings which is a direct dictionary
                    if section == 'component_llm_mappings':
                        self._config.component_llm_mappings = settings
                        if self._logger:
                            self._logger.debug(f"Updated component_llm_mappings with {settings}")
                        continue
                    
                    # Handle special case for llm_templates
                    if section == 'llm_templates':
                        # Convert dictionary to LLMConfig objects
                        for template_name, template_data in settings.items():
                            # Create settings object if exists
                            settings_data = template_data.get('settings')
                            settings_obj = None
                            if settings_data:
                                settings_obj = LLMSettings(
                                    temperature=settings_data.get('temperature', 0.7),
                                    max_tokens=settings_data.get('max_tokens'),
                                    verify_ssl=settings_data.get('verify_ssl', True),
                                    timeout=settings_data.get('timeout', 240),
                                    max_image_dimension=settings_data.get('max_image_dimension', 1200),
                                    reasoning_effort=settings_data.get('reasoning_effort', 'medium')
                                )
                                
                            # Create LLMConfig object
                            self._config.llm_templates[template_name] = LLMConfig(
                                provider=template_data.get('provider', 'openai'),
                                model=template_data.get('model', template_name),
                                settings=settings_obj or LLMSettings(),
                                api_key=template_data.get('api_key'),
                                base_url=template_data.get('base_url')
                            )
                        continue
                    
                    # Get the section config object (e.g., self._config.general)
                    section_config = getattr(self._config, section)
                    
                    # Handle section-level dictionaries (e.g., llm_templates)
                    if isinstance(settings, dict) and isinstance(section_config, dict):
                        section_config.update(settings)
                        continue
                    
                    # Handle dataclass sections
                    if hasattr(section_config, '__dict__'):
                        for key, value in settings.items():
                            # Special case for nested dataclasses
                            if key == 'trusty_agents' and hasattr(section_config, key):
                                trusty_config = getattr(section_config, key)
                                for trusty_key, trusty_value in value.items():
                                    if hasattr(trusty_config, trusty_key):
                                        setattr(trusty_config, trusty_key, trusty_value)
                            # Regular attributes
                            elif hasattr(section_config, key):
                                setattr(section_config, key, value)
            
            if self._logger:
                self._logger.info(f"Configuration loaded from {config_file}")
                
        except Exception as e:
            if self._logger:
                self._logger.error(f"Error loading configuration: {e}")

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

    def get_llm_config(self, llm_type: Optional[str] = None, component: str = None) -> LLMConfig:
        """Get LLM configuration for specified type or component.
        
        Args:
            llm_type: Legacy parameter for backward compatibility - "weak", "strong", or "vision"
            component: Component name to get LLM config for (preferred method)
            
        Returns:
            LLMConfig configuration for the specified component or type
        """
        # If component is specified, use the component mapping directly and ignore llm_type
        if component:
            template_name = self._config.component_llm_mappings.get(component)
            if not template_name:
                self._logger.warning(
                    f"No template mapping for component '{component}', using default"
                )
                template_name = self._config.component_llm_mappings.get("default")
                
            # Get the template config
            if template_name in self._config.llm_templates:
                return self._config.llm_templates[template_name]
            else:
                # Template name was set in mapping but doesn't exist in templates
                self._logger.warning(
                    f"Template '{template_name}' mapped for component '{component}' not found, creating on-the-fly"
                )
                # Create a default config with the template name as the model name
                return LLMConfig(
                    provider="openai",
                    model=template_name,
                    settings=LLMSettings(
                        temperature=0.7,
                        max_tokens=None,
                        verify_ssl=True,
                        timeout=120,
                        reasoning_effort="medium"
                    )
                )
        
        # If component was not provided, use default
        if self._logger:
            self._logger.warning("Component not specified for get_llm_config, using default.")
        return self.get_llm_config(component="default")

    @property
    def logging(self) -> LoggingConfig:
        """Get logging configuration."""
        return self._config.logging

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from config by key with a default."""
        return getattr(self._config, key, default)

    def safe_get(self, *keys: str) -> Any:
        """Safely get a nested config value using dot notation.
        Uses the default values defined in the config classes themselves.
        
        Args:
            *keys: Variable number of keys to traverse the config hierarchy
            
        Example:
            config.safe_get('general', 'max_retries_block_creation')
            config.safe_get('git', 'enabled')
        """
        current = self._config
        for key in keys:
            if not hasattr(current, key):
                # Get the default value from the config class
                config_class = type(current)
                if hasattr(config_class, key):
                    return getattr(config_class, key)
                return None
            current = getattr(current, key)
        return current

    def debug_model_mappings(self):
        """Print current component -> template -> provider/model mappings."""
        if self._logger:
            self._logger.info("Current component -> template -> provider/model mappings:")
            for component, template in self._config.component_llm_mappings.items():
                model_config = self._config.llm_templates.get(template)
                if model_config:
                    provider = model_config.provider
                    model_name = model_config.model
                    self._logger.info(f"{component:20} -> {template:20} -> {provider}/{model_name}")
                else:
                    self._logger.info(f"{component:20} -> {template:20} -> MISSING TEMPLATE")

    def debug_templates(self):
        """Print all template definitions."""
        if self._logger:
            self._logger.info("Current template definitions:")
            for template_name, template_config in self._config.llm_templates.items():
                self._logger.info(f"Template: {template_name}")
                self._logger.info(f"  Provider: {template_config.provider}")
                self._logger.info(f"  Model: {template_config.model}")
                self._logger.info(f"  Settings: {vars(template_config.settings)}")
                self._logger.info("---")

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
                # Normalize the key by converting underscores to hyphens
                normalized_key = key.replace("_", "-")
                
                if normalized_key.startswith("general-"):
                    subkey = normalized_key[len("general-"):].replace("-", "_")
                    if hasattr(self._config.general, subkey):
                        setattr(self._config.general, subkey, value)
                        if self._logger:
                            self._logger.debug(f"Set general config {subkey}={value} from prefixed arg")
                elif normalized_key.startswith("git-"):
                    subkey = normalized_key[len("git-"):].replace("-", "_")
                    if hasattr(self._config.git, subkey):
                        setattr(self._config.git, subkey, value)
                        if self._logger:
                            self._logger.debug(f"Set git config {subkey}={value} from prefixed arg")
                # Handle unprefixed arguments that match general config keys
                elif normalized_key.replace("-", "_") in vars(self._config.general):
                    subkey = normalized_key.replace("-", "_")
                    setattr(self._config.general, subkey, value)
                    if self._logger:
                        self._logger.debug(f"Set general config {subkey}={value} from unprefixed arg")
                elif hasattr(self._config, normalized_key.replace("-", "_")):
                    setattr(self._config, normalized_key.replace("-", "_"), value)
                    if self._logger:
                        self._logger.debug(f"Set root config {normalized_key.replace('-', '_')}={value}")
        
        if self._logger:
            self._logger.debug(f"Final general config after override: {vars(self._config.general)}")

    def override_with_dict(self, config_dict: Dict[str, Any]) -> None:
        """Override configuration values with a nested dictionary.
        
        The dictionary should have top-level keys matching config sections
        (general, git, aider, etc.) with nested dictionaries of settings.
        
        Example:
            {
                'general': {'coding_agent': 'aider'},
                'git': {'auto_commit_if_success': False},
                'component_llm_mappings': {'chat': 'gemini-1.5-pro'}
            }
        """
        self._setup_logger()

        if self._logger:
            self._logger.debug(f"Overriding config with dict: {config_dict}")

        for section, settings in config_dict.items():
            # Handle direct attributes on the Config class (component_llm_mappings, etc.)
            if hasattr(self._config, section) and not isinstance(settings, dict):
                setattr(self._config, section, settings)
                if self._logger:
                    self._logger.debug(f"Set direct config attribute {section}={settings}")
                continue
            
            # Handle dictionary attributes on the Config class (component_llm_mappings, etc.)
            if hasattr(self._config, section) and isinstance(settings, dict) and isinstance(getattr(self._config, section), dict):
                current_dict = getattr(self._config, section)
                current_dict.update(settings)
                if self._logger:
                    self._logger.debug(f"Updated dictionary attribute {section} with {settings}")
                continue
                
            # Handle nested configuration sections
            if hasattr(self._config, section) and isinstance(settings, dict):
                section_config = getattr(self._config, section)
                if hasattr(section_config, '__dict__'):  # If it's a dataclass or has attributes
                    for key, value in settings.items():
                        if hasattr(section_config, key):
                            setattr(section_config, key, value)
                            if self._logger:
                                self._logger.debug(f"Set {section} config {key}={value}")
                        else:
                            if self._logger:
                                self._logger.warning(f"Unknown config key '{key}' in section '{section}'")
            else:
                if self._logger:
                    self._logger.warning(f"Unknown config section: {section}")


# Global instance
config = ConfigManager() 
