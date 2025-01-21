"""Module for configuring logging."""

import colorlog
import logging
import os
import yaml

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
    """Setup logging configuration based on config.yaml"""
    # Load config
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'config.yaml')
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    # Create logger
    logger = logging.getLogger('tdac')
    
    # Remove any existing handlers
    logger.handlers = []
    
    # Prevent the logger from propagating messages to the root logger
    logger.propagate = False
    
    # Create console handler
    console_handler = colorlog.StreamHandler()
    
    # Create formatter
    log_colors = {
        'DEBUG': 'cyan',
        'INFO': config['logging']['tdac']['color'],
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'red,bg_white',
    }
    
    formatter = colorlog.ColoredFormatter(
        '%(log_color)s%(message)s%(reset)s',
        log_colors=log_colors,
        reset=True
    )
    
    # Add formatter to console handler
    console_handler.setFormatter(formatter)
    
    # Add console handler to logger
    logger.addHandler(console_handler)
    
    # Set level from config
    logger.setLevel(config['logging']['tdac']['level'])
    
    return logger

# Create and expose the logger
logger = setup_logging() 