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
    
    def __init__(self, name, level=logging.NOTSET):
        super().__init__(name, level)
        self._heading_attempt_count = 0
    
    def info(self, msg, *args, heading=False, **kwargs):
        """
        Log an info message with optional heading formatting.
        
        Args:
            msg: The message to log
            heading: If True, add screen-width separators before and after the message
            *args, **kwargs: Standard logging arguments
        """
        if heading:
            self._heading_attempt_count += 1
            kwargs.setdefault('extra', {})['heading'] = True
            kwargs['extra']['attempt_count'] = self._heading_attempt_count
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
            self._heading_attempt_count += 1
            kwargs.setdefault('extra', {})['heading'] = True
            kwargs['extra']['attempt_count'] = self._heading_attempt_count
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
            self._heading_attempt_count += 1
            kwargs.setdefault('extra', {})['heading'] = True
            kwargs['extra']['attempt_count'] = self._heading_attempt_count
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
            self._heading_attempt_count += 1
            kwargs.setdefault('extra', {})['heading'] = True
            kwargs['extra']['attempt_count'] = self._heading_attempt_count
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
            self._heading_attempt_count += 1
            kwargs.setdefault('extra', {})['heading'] = True
            kwargs['extra']['attempt_count'] = self._heading_attempt_count
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
    logger = logging.getLogger(name if name else 'tac')
    if logger.handlers:
        logger.handlers.clear()
    logger.propagate = False
    console_handler = logging.StreamHandler(sys.__stdout__)
    
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
            orig_levelname = record.levelname
            if orig_levelname in self.COLORS:
                record.levelname = f"{self.COLORS[orig_levelname]}{orig_levelname}{Style.RESET_ALL}"
            
            is_heading = hasattr(record, 'heading') and record.heading
            terminal_width = shutil.get_terminal_size().columns
            formatted_msg = super().format(record)
            
            if is_heading:
                separator = '=' * terminal_width
                attempt = getattr(record, 'attempt_count', 'N/A')
                additional_details = f"[PID: {os.getpid()}, Attempt: {attempt}]"
                formatted_msg = f"\n{separator}\n{formatted_msg}\n{additional_details}\n{separator}"
            
            record.levelname = orig_levelname
            return formatted_msg
    
    colored_formatter = ColoredFormatter('%(levelname)s - %(message)s [%(name)s]')
    console_handler.setFormatter(colored_formatter)
    logger.addHandler(console_handler)
    logger.propagate = False
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
    numeric_level = logging.DEBUG
    if logging.getLogger().getEffectiveLevel() >= logging.CRITICAL:
        logger = logging.getLogger(name if name else 'tac')
        logger.setLevel(logging.CRITICAL)
        logger.propagate = False
        return logger
        
    if execution_id is not None:
        execution_context.execution_id = execution_id
    
    if name in _configured_loggers:
        logger = _configured_loggers[name]
        logger.setLevel(numeric_level)
        for handler in logger.handlers:
            handler.setLevel(numeric_level)
        return logger

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
            orig_levelname = record.levelname
            if orig_levelname in self.COLORS:
                record.levelname = f"{self.COLORS[orig_levelname]}{orig_levelname}{Style.RESET_ALL}"
            
            is_heading = hasattr(record, 'heading') and record.heading
            terminal_width = shutil.get_terminal_size().columns
            formatted_msg = super().format(record)
            if is_heading:
                separator = '=' * terminal_width
                attempt = getattr(record, 'attempt_count', 'N/A')
                additional_details = f"[PID: {os.getpid()}, Attempt: {attempt}]"
                formatted_msg = f"\n{separator}\n{formatted_msg}\n{additional_details}\n{separator}"
            record.levelname = orig_levelname
            return formatted_msg

    root = logging.getLogger()
    if not root.handlers:
        root_handler = logging.StreamHandler(sys.__stdout__)
        root_handler.setLevel(logging.WARNING)
        root_handler.setFormatter(ColoredFormatter('%(levelname)s - %(message)s [%(name)s]'))
        root.addHandler(root_handler)
        root.setLevel(logging.WARNING)

    logger = logging.getLogger(name if name else 'tac')
    logger.propagate = False
    if logger.handlers:
        logger.handlers.clear()
    logger.setLevel(numeric_level)
    console_handler = logging.StreamHandler(sys.__stdout__)
    console_handler.setLevel(numeric_level)
    colored_formatter = ColoredFormatter('%(levelname)s - %(message)s [%(name)s]')
    console_handler.setFormatter(colored_formatter)
    logger.addHandler(console_handler)
    
    try:
        now = datetime.datetime.now()
        timestamp = now.strftime("%y%m%d_%H%M")
        logs_dir = '.tac_logs'
        if not os.path.isabs(logs_dir):
            logs_dir = os.path.join(os.getcwd(), logs_dir)
        os.makedirs(logs_dir, exist_ok=True)
        log_filename = os.path.join(logs_dir, f"{timestamp}_log.txt")
        file_handler = logging.FileHandler(log_filename, mode='a')
        file_handler.setLevel(numeric_level)
        
        class FileFormatter(logging.Formatter):
            def format(self, record):
                timestamp_dt = datetime.datetime.fromtimestamp(record.created)
                timestamp_str = timestamp_dt.strftime("%y%m%d %H:%M %S.%f")[:-4]
                is_heading = hasattr(record, 'heading') and record.heading
                msg = f"{record.levelname} - {record.getMessage()} [{record.name} {timestamp_str}]"
                if is_heading:
                    separator = '=' * 80
                    attempt = getattr(record, 'attempt_count', 'N/A')
                    additional_details = f"[PID: {os.getpid()}, Attempt: {attempt}]"
                    msg = f"\n{separator}\n{msg}\n{additional_details}\n{separator}"
                return msg
        
        file_formatter = FileFormatter()
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        logger.debug(f"Debug logging started to file: {log_filename}")
    except Exception as e:
        logger.warning(f"Failed to set up file logging: {str(e)}")

    _configured_loggers[name] = logger
    return logger

def get_current_execution_id():
    """Get the current execution ID."""
    return execution_context.execution_id

def reset_execution_context():
    """Reset the execution context for a new run."""
    execution_context.reset()
    _configured_loggers.clear()

def update_all_loggers(log_level: str = 'INFO'):
    """Update all existing loggers with a new log level.
    
    Args:
        log_level: The new log level to set for all handlers
    """
    numeric_level = logging.DEBUG
    for name, logger in _configured_loggers.items():
        logger.setLevel(numeric_level)
        for handler in logger.handlers:
            handler.setLevel(numeric_level)
    root = logging.getLogger()
    if root.handlers:
        for handler in root.handlers:
            handler.setLevel(numeric_level)

logger = setup_logging() 