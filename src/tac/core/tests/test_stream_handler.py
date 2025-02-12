import sys
import logging
import unittest
from src.tac.core.log_config import setup_logging

class TestStreamHandlerStdout(unittest.TestCase):
    def test_stream_handler_stdout(self):
        logger = setup_logging("test_stream_stdout")
        handler_found = False
        for handler in logger.handlers:
            if isinstance(handler, logging.StreamHandler):
                self.assertEqual(handler.stream, sys.__stdout__)
                handler_found = True
                break
        self.assertTrue(handler_found, "No StreamHandler found in logger")

if __name__ == "__main__":
    unittest.main()
