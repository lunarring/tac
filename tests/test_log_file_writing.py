import os
import glob
import logging
from tac.core.log_config import setup_logging, reset_execution_context

def test_log_file_written(tmp_path, monkeypatch):
    # Change the current working directory to the temporary directory
    monkeypatch.chdir(tmp_path)
    
    # Reset execution context to ensure a fresh logger is created
    reset_execution_context()
    
    # Setup logger with a unique name to avoid conflicts and use DEBUG level to capture all logs
    logger = setup_logging("test_logger", log_level="DEBUG")
    test_message = "Test error message"
    
    # Log an error message
    logger.error(test_message)
    
    # Flush file handlers to ensure the message is written
    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler):
            handler.flush()
    
    # The log directory should be created under the current working directory (i.e., tmp_path/.tac_logs)
    log_dir = tmp_path / ".tac_logs"
    assert log_dir.exists() and log_dir.is_dir(), "Log directory not created"
    
    # Find the log file created in the logs directory
    log_files = list(log_dir.glob("*_log.txt"))
    assert len(log_files) > 0, "No log file created in the log directory"
    
    # Check that the log file contains the test message
    log_file = log_files[0]
    with open(log_file, "r") as f:
        content = f.read()
    assert test_message in content, "Logged message not found in the log file"
    
    # Cleanup is handled by the tmp_path fixture automatically
     
if __name__ == "__main__":
    import pytest
    pytest.main([__file__])
    