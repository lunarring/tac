"""Module for configuring logging."""

import logging
import os
from colorama import Fore, Style, init
import sys
import time
import datetime
import shutil

# Initialize colorama
init()

# Store configured loggers to prevent duplicate setup
_configured_loggers = {}

def get_log_level(name: str = None, default_level: str = 'INFO') -> str:
    """Get the log level, with fallback to default value.
    
    Args:
        name: The logger name to get level for
        default_level: The default level to return if not configured
        
    Returns:
        The log level as a string
    """
    # Check environment variable first (highest priority)
    env_var = os.environ.get('TAC_LOG_LEVEL')
    if env_var:
        return env_var.upper()
        
    # Try to get from config if available
    try:
        from tac.core.config import config
        if hasattr(config, 'logging'):
            if name and hasattr(config.logging, name):
                return config.safe_get('logging', name).get('level', default_level)
            # Fall back to general TAC level
            return config.safe_get('logging', 'tac', 'level') or default_level
    except (ImportError, AttributeError):
        pass
        
    return default_level

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

# Monkey patch the standard Logger class to add heading parameter to all log methods
# This is a simpler approach than trying to replace all loggers
original_log = logging.Logger._log

def _patched_log(self, level, msg, args, exc_info=None, extra=None, stack_info=False, stacklevel=1, heading=False, **kwargs):
    """
    Patched _log method that handles the heading parameter.
    """
    if heading:
        if extra is None:
            extra = {}
        extra['heading'] = True
    
    return original_log(self, level, msg, args, exc_info, extra, stack_info, stacklevel)

# Apply the monkey patch
logging.Logger._log = _patched_log

class TACLogger(logging.Logger):
    """Custom logger class that extends the standard Logger with additional features."""
    
    def info(self, msg, *args, heading=False, **kwargs):
        """
        Log an info message with optional heading formatting.
        
        Args:
            msg: The message to log
            heading: If True, add screen-width separators before and after the message
            *args, **kwargs: Standard logging arguments
        """
        if heading:
            # Store heading flag in extra dict
            kwargs.setdefault('extra', {})['heading'] = True
        
        # Call the parent info method
        super().info(msg, *args, **kwargs)
    
    def debug(self, msg, *args, heading=False, **kwargs):
        """
        Log a debug message with optional heading formatting.
        
        Args:
            msg: The message to log
            heading: If True, add screen-width separators before and after the message
            *args, **kwargs: Standard logging arguments
        """
        if heading:
            # Store heading flag in extra dict
            kwargs.setdefault('extra', {})['heading'] = True
        
        # Call the parent debug method
        super().debug(msg, *args, **kwargs)
    
    def warning(self, msg, *args, heading=False, **kwargs):
        """
        Log a warning message with optional heading formatting.
        
        Args:
            msg: The message to log
            heading: If True, add screen-width separators before and after the message
            *args, **kwargs: Standard logging arguments
        """
        if heading:
            # Store heading flag in extra dict
            kwargs.setdefault('extra', {})['heading'] = True
        
        # Call the parent warning method
        super().warning(msg, *args, **kwargs)
    
    def error(self, msg, *args, heading=False, **kwargs):
        """
        Log an error message with optional heading formatting.
        
        Args:
            msg: The message to log
            heading: If True, add screen-width separators before and after the message
            *args, **kwargs: Standard logging arguments
        """
        if heading:
            # Store heading flag in extra dict
            kwargs.setdefault('extra', {})['heading'] = True
        
        # Call the parent error method
        super().error(msg, *args, **kwargs)
    
    def critical(self, msg, *args, heading=False, **kwargs):
        """
        Log a critical message with optional heading formatting.
        
        Args:
            msg: The message to log
            heading: If True, add screen-width separators before and after the message
            *args, **kwargs: Standard logging arguments
        """
        if heading:
            # Store heading flag in extra dict
            kwargs.setdefault('extra', {})['heading'] = True
        
        # Call the parent critical method
        super().critical(msg, *args, **kwargs)

# Register our custom logger class
logging.setLoggerClass(TACLogger)

def setup_console_logging(name: str = None, log_level: str = 'INFO') -> logging.Logger:
    """
    Setup logging configuration for console only (no log files)
    
    Args:
        name: Logger name
        log_level: Logging level to use (default: INFO)
    """
    # Create a new logger
    logger = logging.getLogger(name if name else 'tac')
    
    # Remove any existing handlers
    if logger.handlers:
        logger.handlers.clear()
    
    # Prevent propagation to root logger
    logger.propagate = False
    
    # Set logger level (enforcing DEBUG level)
    logger.setLevel(logging.DEBUG)
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.__stdout__)
    console_handler.setLevel(logging.DEBUG)
    
    # Create formatter and add it to the handler
    log_format = '%(levelname)s - %(message)s [%(name)s]'
    
    # Create custom formatter
    class ColoredFormatter(logging.Formatter):
        """Custom formatter class to add colors to log levels"""
        
        COLORS = {
            'DEBUG': Fore.BLUE,
            'INFO': Fore.GREEN,
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
            
            # Check if this is a heading
            is_heading = hasattr(record, 'heading') and record.heading
            
            # Get terminal width
            terminal_width = shutil.get_terminal_size().columns
            
            # Format the message
            formatted_msg = super().format(record)
            
            # Add separators for headings
            if is_heading:
                separator = '=' * terminal_width
                formatted_msg = f"\n{separator}\n{formatted_msg}\n{separator}"
            
            # Restore original levelname
            record.levelname = orig_levelname
            return formatted_msg
    
    colored_formatter = ColoredFormatter(log_format)
    console_handler.setFormatter(colored_formatter)

    # Add the handler to the logger
    logger.addHandler(console_handler)
    
    # Store the configured logger to prevent duplicate setup
    _configured_loggers[name] = logger
    
    return logger

def setup_logging(name: str = None, execution_id: int = None, log_level: str = 'INFO', log_color: str = 'green') -> logging.Logger:
    """
    Setup logging configuration
    
    Args:
        name: Logger name
        execution_id: Optional execution ID to use for log files
        log_level: Logging level to use for console output (default: INFO)
        log_color: Color to use for logging (default: green)
    """
    # Force DEBUG level throughout the application runtime
    numeric_level = logging.DEBUG
    
    # If logging is disabled (level set to CRITICAL), just return a disabled logger
    if logging.getLogger().getEffectiveLevel() >= logging.CRITICAL:
        logger = logging.getLogger(name if name else 'tac')
        logger.setLevel(logging.CRITICAL)
        logger.propagate = False
        return logger
        
    # If execution_id is provided, set it in the context
    if execution_id is not None:
        execution_context.execution_id = execution_id
    
    # If this logger was already configured, update its level and return it
    if name in _configured_loggers:
        logger = _configured_loggers[name]
        logger.setLevel(numeric_level)
        for handler in logger.handlers:
            handler.setLevel(numeric_level)
        return logger

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
            
            # Check if this is a heading
            is_heading = hasattr(record, 'heading') and record.heading
            
            # Get terminal width
            terminal_width = shutil.get_terminal_size().columns
            
            # Format the message
            formatted_msg = super().format(record)
            
            # Add separators for headings
            if is_heading:
                separator = '=' * terminal_width
                formatted_msg = f"\n{separator}\n{formatted_msg}\n{separator}"
            
            # Restore original levelname
            record.levelname = orig_levelname
            return formatted_msg

    # Configure root logger first
    root = logging.getLogger()
    if not root.handlers:  # Only configure root once
        root_handler = logging.StreamHandler(sys.__stdout__)
        # Set root to WARNING level by default
        root_handler.setLevel(logging.WARNING)
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
    
    # Set logger level to the enforced DEBUG level
    logger.setLevel(numeric_level)

    # Create console handler with the specified level
    console_handler = logging.StreamHandler(sys.__stdout__)
    console_handler.setLevel(numeric_level)

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
        file_handler.setLevel(numeric_level)
        
        # Create a custom formatter for file logs with the requested format
        # LEVEL - MESSAGE - SOURCE - TIMESTAMP
        class FileFormatter(logging.Formatter):
            def format(self, record):
                # Format timestamp as YYMMDD HH:MM SS.SS
                timestamp = datetime.datetime.fromtimestamp(record.created)
                timestamp_str = timestamp.strftime("%y%m%d %H:%M %S.%f")[:-4]
                
                # Check if this is a heading
                is_heading = hasattr(record, 'heading') and record.heading
                
                # Format the log message
                msg = f"{record.levelname} - {record.getMessage()} [{record.name} {timestamp_str}]"
                
                # Add separators for headings in file logs too
                if is_heading:
                    separator = '=' * 80  # Fixed width for file logs
                    msg = f"\n{separator}\n{msg}\n{separator}"
                
                return msg
        
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

def update_all_loggers(log_level: str = 'INFO'):
    """Update all existing loggers with a new log level.
    
    Args:
        log_level: The new log level to set for all handlers
    """
    # Force DEBUG level regardless of the provided log_level
    numeric_level = logging.DEBUG
    
    # Update all configured loggers
    for name, logger in _configured_loggers.items():
        # Set the logger level to the new numeric level
        logger.setLevel(numeric_level)
        # Update all handlers to the new numeric level
        for handler in logger.handlers:
            handler.setLevel(numeric_level)
                
    # Also update the root logger for good measure
    root = logging.getLogger()
    if root.handlers:
        for handler in root.handlers:
            handler.setLevel(numeric_level)

# Create and expose the default logger
logger = setup_logging() 