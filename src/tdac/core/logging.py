import logging
import colorlog
import os
import yaml

def setup_logging():
    """Setup logging configuration based on config.yaml"""
    # Load config
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'config.yaml')
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    # Create logger
    logger = logging.getLogger('test_chain')
    
    # Remove any existing handlers
    logger.handlers = []
    
    # Prevent the logger from propagating messages to the root logger
    logger.propagate = False
    
    # Create console handler
    console_handler = colorlog.StreamHandler()
    
    # Create formatter
    log_colors = {
        'DEBUG': 'cyan',
        'INFO': config['logging']['test_chain']['color'],
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
    logger.setLevel(config['logging']['test_chain']['level'])
    
    return logger

# Create and expose the logger
logger = setup_logging() 