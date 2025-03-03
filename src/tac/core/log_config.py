"""Module for configuring logging."""

import logging
import os
from colorama import Fore, Style, init
import sys
import time
import datetime
from tac.core.config import config

# Initialize colorama
init()

# Store configured loggers to prevent duplicate setup
_configured_loggers = {}

class ExecutionContext:
    """
    Singleton class to manage execution context including ID.
    This avoids using global variables while providing a centralized
    way to access execution information.
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ExecutionContext, cls).__new__(cls)
            cls._instance._execution_id = None
        return cls._instance
    
    @property
    def execution_id(self):
        """Get the current execution ID or generate a new one."""
        if self._execution_id is None:
            self._execution_id = int(time.time())
        return self._execution_id
    
    @execution_id.setter
    def execution_id(self, value):
        """Set the execution ID explicitly."""
        self._execution_id = value
    
    def reset(self):
        """Reset the execution context."""
        self._execution_id = None

# Create a singleton instance
execution_context = ExecutionContext()

def get_log_level(name: str = None) -> str:
    """Get the log level from config, with fallback to default values."""
    try:
        if hasattr(config, 'logging'):
            return config.logging.get_tac('level', 'INFO')
        return 'INFO'
    except Exception:
        return 'INFO'

def setup_logging(name: str = None, execution_id: int = None) -> logging.Logger:
    """
    Setup logging configuration
    
    Args:
        name: Logger name
        execution_id: Optional execution ID to use for log files
    """
    # If execution_id is provided, set it in the context
    if execution_id is not None:
        execution_context.execution_id = execution_id
    
    # If this logger was already configured, return it
    if name in _configured_loggers:
        return _configured_loggers[name]

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
        root_handler = logging.StreamHandler(sys.__stdout__)
        root_handler.setLevel(logging.WARNING)  # Set root to WARNING level
        root_handler.setFormatter(ColoredFormatter('%(levelname)s - %(message)s [%(name)s]'))
        root.addHandler(root_handler)
        root.setLevel(logging.WARNING)

    # Get or create logger
    logger = logging.getLogger(name if name else 'tac')
    
    # Prevent propagation to root logger
    logger.propagate = False
    
    # Remove any existing handlers
    if logger.handlers:
        logger.handlers.clear()
    
    # Get console and file log levels from config
    console_log_level = get_log_level(name)
    file_log_level = 'DEBUG'  # Always save all logs including DEBUG to file
    
    # Set logger level to the minimum of console and file log levels to ensure all messages are processed
    logger_level = min(
        getattr(logging, console_log_level),
        getattr(logging, file_log_level)
    )
    logger.setLevel(logger_level)

    # Create console handler
    console_handler = logging.StreamHandler(sys.__stdout__)
    console_handler.setLevel(getattr(logging, console_log_level))

    # Create formatter and add it to the handler
    log_format = '%(levelname)s - %(message)s [%(name)s]'
    colored_formatter = ColoredFormatter(log_format)
    console_handler.setFormatter(colored_formatter)

    # Add the handler to the logger
    logger.addHandler(console_handler)
    
    # Always enable file logging with the new format
    try:
        # Create timestamp for log filename in YYMMDD_HHMM format
        now = datetime.datetime.now()
        timestamp = now.strftime("%y%m%d_%H%M")
        
        # Create log directory
        logs_dir = '.tac_logs'
        
        # Handle relative paths
        if not os.path.isabs(logs_dir):
            logs_dir = os.path.join(os.getcwd(), logs_dir)
            
        # Create directory if it doesn't exist
        os.makedirs(logs_dir, exist_ok=True)
        
        # Create log filename with timestamp
        log_filename = os.path.join(logs_dir, f"{timestamp}_log.txt")
        
        # Create file handler
        file_handler = logging.FileHandler(log_filename, mode='a')
        
        # Set file handler level to DEBUG to capture all logs
        file_handler.setLevel(logging.DEBUG)
        
        # Create a custom formatter for file logs with the requested format
        # LEVEL - MESSAGE - SOURCE - TIMESTAMP
        class FileFormatter(logging.Formatter):
            def format(self, record):
                # Format timestamp as YYMMDD HH:MM SS.SS
                timestamp = datetime.datetime.fromtimestamp(record.created)
                timestamp_str = timestamp.strftime("%y%m%d %H:%M %S.%f")[:-4]
                
                # Format the log message
                return f"{record.levelname} - {record.getMessage()} [{record.name} {timestamp_str}]"
        
        file_formatter = FileFormatter()
        file_handler.setFormatter(file_formatter)
        
        # Add the file handler to the logger
        logger.addHandler(file_handler)
        
        # Log that we've started file logging
        logger.debug(f"Debug logging started to file: {log_filename}")
    except Exception as e:
        # If file logging setup fails, log to console but don't crash
        logger.warning(f"Failed to set up file logging: {str(e)}")

    # Store the configured logger
    _configured_loggers[name] = logger

    return logger

def get_current_execution_id():
    """Get the current execution ID."""
    return execution_context.execution_id

def reset_execution_context():
    """Reset the execution context for a new run."""
    execution_context.reset()
    # Also clear configured loggers to force recreation
    _configured_loggers.clear()

# Create and expose the default logger
logger = setup_logging() 
