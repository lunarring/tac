"""Module for configuring logging."""

import colorlog
import logging
import os
import yaml
from colorama import Fore, Style
import sys

def setup_logger(name: str, level: str = "INFO", color: str = "white") -> logging.Logger:
    """Set up a colored logger."""
    logger = logging.getLogger(name)
    
    if not logger.handlers:  # Only add handler if it doesn't exist
        handler = colorlog.StreamHandler()
        handler.setFormatter(
            colorlog.ColoredFormatter(
                "%(log_color)s%(levelname)-8s%(reset)s %(blue)s%(name)s%(reset)s: %(message)s",
                log_colors={
                    'DEBUG': color,
                    'INFO': color,
                    'WARNING': 'yellow',
                    'ERROR': 'red',
                    'CRITICAL': 'red,bg_white',
                }
            )
        )
        logger.addHandler(handler)
    
    logger.setLevel(level)
    return logger

def setup_logging():
    """Setup logging configuration"""
    # Load config file
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'config.yaml')
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    # Create custom formatter
    class ColoredFormatter(logging.Formatter):
        """Custom formatter class to add colors to log levels"""
        
        COLORS = {
            'DEBUG': Fore.BLUE,
            'INFO': config['logging']['tac']['color'],
            'WARNING': Fore.YELLOW,
            'ERROR': Fore.RED,
            'CRITICAL': Fore.RED + Style.BRIGHT,
        }

        def format(self, record):
            # Add color to the level name
            levelname = record.levelname
            if levelname in self.COLORS:
                record.levelname = f"{self.COLORS[levelname]}{levelname}{Style.RESET_ALL}"
            return super().format(record)

    # Create logger
    logger = logging.getLogger('tac')
    logger.setLevel(config['logging']['tac']['level'])

    # Create console handler with a higher log level
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)

    # Create formatters and add it to the handlers
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    colored_formatter = ColoredFormatter(log_format)
    console_handler.setFormatter(colored_formatter)

    # Add the handlers to the logger
    logger.addHandler(console_handler)

    return logger

# Create and expose the logger
logger = setup_logging() 