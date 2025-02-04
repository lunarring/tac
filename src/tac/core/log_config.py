"""Module for configuring logging."""

import logging
import os
import yaml
from colorama import Fore, Style, init
import sys

# Initialize colorama
init()

# Store configured loggers to prevent duplicate setup
_configured_loggers = {}

def setup_logging(name: str = None) -> logging.Logger:
    """Setup logging configuration"""
    # If this logger was already configured, return it
    if name in _configured_loggers:
        return _configured_loggers[name]
        
    # Load config file
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'config.yaml')
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    # Create custom formatter
    class ColoredFormatter(logging.Formatter):
        """Custom formatter class to add colors to log levels"""
        
        COLORS = {
            'DEBUG': Fore.BLUE,
            'INFO': Fore.GREEN,  # Default to green if not specified in config
            'WARNING': Fore.YELLOW,
            'ERROR': Fore.RED,
            'CRITICAL': Fore.RED + Style.BRIGHT,
        }

        def format(self, record):
            # Save original levelname
            orig_levelname = record.levelname
            # Add color to the level name
            if orig_levelname in self.COLORS:
                record.levelname = f"{self.COLORS[orig_levelname]}{orig_levelname}{Style.RESET_ALL}"
            formatted_msg = super().format(record)
            # Restore original levelname
            record.levelname = orig_levelname
            return formatted_msg

    # Configure root logger first
    root = logging.getLogger()
    if not root.handlers:  # Only configure root once
        root_handler = logging.StreamHandler(sys.stdout)
        root_handler.setLevel(logging.WARNING)  # Set root to WARNING level
        root_handler.setFormatter(ColoredFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        root.addHandler(root_handler)
        root.setLevel(logging.WARNING)

    # Get or create logger
    logger = logging.getLogger(name if name else 'tac')
    
    # Prevent propagation to root logger
    logger.propagate = False
    
    # Remove any existing handlers
    if logger.handlers:
        logger.handlers.clear()
    
    # Set level from config or default to INFO
    logger.setLevel(config.get('logging', {}).get('tac', {}).get('level', 'INFO'))

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)

    # Create formatter and add it to the handler
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    colored_formatter = ColoredFormatter(log_format)
    console_handler.setFormatter(colored_formatter)

    # Add the handler to the logger
    logger.addHandler(console_handler)

    # Store the configured logger
    _configured_loggers[name] = logger

    return logger

# Create and expose the default logger
logger = setup_logging() 