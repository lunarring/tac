"""
UI utility classes and functions
"""

class NullUIManager:
    """A null object implementation of UIManager that silently ignores all calls."""
    def __init__(self, *args, **kwargs):
        self.block_attempt_count = 0
        self.max_attempts = 4

    def send_status_bar(self, message):
        """No-op implementation"""
        pass
    
    def send_protoblock_data(self, protoblock, attempt_number=None):
        """No-op implementation"""
        pass
    
    def _get_loop(self):
        """Return None as there's no active event loop"""
        return None 