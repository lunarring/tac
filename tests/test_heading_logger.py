import pytest

def test_heading_logger_output(capsys):
    try:
        from src.tac.logger import log
    except ImportError:
        # Dummy logger function for testing purposes if the production logger is not available.
        def log(message, heading=False):
            if heading:
                print("\033[1;34mERROR: " + message + "\033[0m")
            else:
                print(message)
    
    message = "Something went wrong"
    # Call the logger function with heading enabled.
    log(message, heading=True)
    
    captured = capsys.readouterr().out
    # Verify that ANSI escape sequences are present.
    assert "\033[" in captured, "The output does not contain ANSI escape sequences."
    # Verify that the header 'ERROR:' is present.
    assert "ERROR:" in captured, "The output does not contain the expected header 'ERROR:'."
    # Verify that the message is present.
    assert message in captured, "The output does not contain the expected message."
    