#!/usr/bin/env python
"""
Simple script to test logging configuration.
"""
import sys
import os

# Add the src directory to Python path for local development
src_dir = os.path.abspath(os.path.dirname(__file__))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from tac.core.log_config import setup_logging

def main():
    # Test with different log levels
    for level in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
        print(f"\nTesting log level: {level}")
        logger = setup_logging('test', log_level=level)
        
        # Log messages at different levels
        logger.debug("This is a DEBUG message")
        logger.info("This is an INFO message")
        logger.warning("This is a WARNING message")
        logger.error("This is an ERROR message")
        logger.critical("This is a CRITICAL message")

if __name__ == "__main__":
    main() 