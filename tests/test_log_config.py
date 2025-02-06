import unittest
import logging
import io
from unittest.mock import patch

from src.tac.core.log_config import setup_logging

class TestLogConfig(unittest.TestCase):
    def setUp(self):
        # Patch the open function in log_config to provide a dummy YAML config.
        self.patcher = patch('src.tac.core.log_config.open', return_value=io.StringIO("logging:\n  tac:\n    level: ERROR\n"))
        self.mock_open = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_logger_setup(self):
        # First invocation of setup_logging
        logger1 = setup_logging("test_logger")
        self.assertIsInstance(logger1, logging.Logger)
        self.assertGreaterEqual(len(logger1.handlers), 1)
        # Ensure that one of the handlers uses custom ColoredFormatter (by checking its class name)
        formatter_found = any("ColoredFormatter" in type(handler.formatter).__name__ for handler in logger1.handlers)
        self.assertTrue(formatter_found, "No handler with a ColoredFormatter found")

        # Second invocation should not add duplicate handlers
        logger2 = setup_logging("test_logger")
        self.assertEqual(len(logger2.handlers), 1, "Duplicate handlers were added on repeated calls to setup_logging")

    def test_log_output_formatting(self):
        logger = setup_logging("test_format")
        # Find a StreamHandler and override its stream with a StringIO to capture log output.
        stream = io.StringIO()
        selected_handler = None
        for handler in logger.handlers:
            if isinstance(handler, logging.StreamHandler):
                selected_handler = handler
                break
        self.assertIsNotNone(selected_handler, "No StreamHandler found in logger")
        # Override the stream for our test.
        selected_handler.stream = stream

        # Log an error message and capture its output
        logger.error("Test error")
        output = stream.getvalue()
        # Assert that ANSI escape sequences (starting with \x1b[) appear and that "ERROR" is present.
        self.assertIn("\x1b[", output, "ANSI escape sequence not found in log output")
        self.assertIn("ERROR", output, "Log output does not contain 'ERROR' log level")

if __name__ == "__main__":
    unittest.main()
