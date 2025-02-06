import unittest
import io
import logging
from src.tac.core.log_config import setup_logging

class TestLogColor(unittest.TestCase):
    def test_ansi_color_error_log(self):
        # Setup the logger
        logger = setup_logging("test_color")
        # Redirect output of the logger's StreamHandler to an in-memory stream
        stream = io.StringIO()
        for handler in logger.handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.stream = stream
                break
        # Emit an error log
        logger.error("Test error")
        output = stream.getvalue()
        # Verify that ANSI escape codes and 'ERROR' appear in the output
        self.assertIn("\x1b[", output, "ANSI escape sequence not found in error log")
        self.assertIn("ERROR", output, "ERROR text not found in error log")

if __name__ == "__main__":
    unittest.main()
