#!/usr/bin/env python
from tac.core.log_config import setup_logging

# Create a logger
logger = setup_logging("test_logger")

# Log a regular message
logger.info("This is a regular info message")

# Log a message with heading=True
logger.info("This is a heading message", heading=True)

# Log another regular message
logger.info("This is another regular message")

# Log another heading
logger.info("Another important heading", heading=True) 