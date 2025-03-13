import io
import logging
import shutil
from tac.core.log_config import TACLogger

def test_immediate_verbose_logging():
    # Set up an in-memory stream and logger for immediate verbose logging
    stream = io.StringIO()
    logger = TACLogger("immediate_verbose_logger")
    # Clear any existing handlers
    logger.handlers.clear()
    # Create stream handler with the in-memory stream
    handler = logging.StreamHandler(stream)

    # Define a formatter that simulates immediate verbose logging output with header separators
    class ImmediateVerboseFormatter(logging.Formatter):
        def format(self, record):
            terminal_width = shutil.get_terminal_size().columns
            formatted_msg = f"{record.levelname} - {record.getMessage()} [{record.name}]"
            if hasattr(record, 'heading') and record.heading:
                separator = '=' * terminal_width
                formatted_msg = f"\n{separator}\n{formatted_msg}\n{separator}"
            return formatted_msg

    handler.setFormatter(ImmediateVerboseFormatter())
    logger.addHandler(handler)
    logger.propagate = False

    test_message = "Immediate verbose logging activated"
    # Log the message with heading=True to simulate immediate verbose mode
    logger.info(test_message, heading=True)
    output = stream.getvalue()

    terminal_width = shutil.get_terminal_size().columns
    separator = '=' * terminal_width
    # Assert that the output includes the header separators and the test message.
    assert separator in output
    assert test_message in output