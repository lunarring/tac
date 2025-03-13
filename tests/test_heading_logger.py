import io
import logging
import re
import shutil
import pytest
from tac.core.log_config import TACLogger

def get_terminal_width():
    try:
        return shutil.get_terminal_size().columns
    except Exception:
        return 80

@pytest.fixture
def in_memory_logger():
    # Create an in-memory stream
    stream = io.StringIO()
    # Create an instance of TACLogger with a unique logger name
    logger = TACLogger("test_logger")
    # Clear any existing handlers
    logger.handlers = []
    # Create stream handler with the in-memory stream
    handler = logging.StreamHandler(stream)
    
    # Define a simple formatter that simulates the heading formatting behavior
    class DummyFormatter(logging.Formatter):
        def format(self, record):
            terminal_width = get_terminal_width()
            formatted_msg = f"{record.levelname} - {record.getMessage()} [{record.name}]"
            if hasattr(record, 'heading') and record.heading:
                separator = '=' * terminal_width
                formatted_msg = f"\n{separator}\n{formatted_msg}\n{separator}"
            return formatted_msg
    
    handler.setFormatter(DummyFormatter())
    logger.addHandler(handler)
    logger.propagate = False
    return logger, stream

def test_heading_formatting(in_memory_logger):
    logger, stream = in_memory_logger
    message = "This is a heading message"
    logger.info(message, heading=True)
    output = stream.getvalue()
    terminal_width = get_terminal_width()
    separator = '=' * terminal_width
    # Assert that the output contains the heading separator before and after the message.
    assert separator in output
    # Ensure the message is present in the output.
    assert message in output

def test_non_heading_formatting(in_memory_logger):
    logger, stream = in_memory_logger
    message = "This is a non-heading message"
    logger.info(message)
    output = stream.getvalue()
    # Ensure that no heading separator (a line of '=') is present.
    pattern = re.compile(r'\n=+\n')
    assert pattern.search(output) is None
    # Ensure the message is present in the output.
    assert message in output