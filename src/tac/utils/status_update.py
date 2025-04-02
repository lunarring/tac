import threading
import logging

# Thread-safe storage for the status message
_current_status = ""
_lock = threading.Lock()

logger = logging.getLogger("status_update")

def update_status(message: str) -> None:
    """
    Update the current status message and log the update.
    
    Args:
        message: The new status message to set.
    """
    global _current_status
    with _lock:
        _current_status = message
    logger.info("Status updated: " + message)

def get_status() -> str:
    """
    Retrieve the current status message.
    
    Returns:
        The current status message.
    """
    with _lock:
        return _current_status