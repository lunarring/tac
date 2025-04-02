import pytest
from tac.utils import status_update

def test_update_get_status():
    # Update the status and then retrieve it to verify consistency.
    status_update.update_status("Test status message")
    retrieved = status_update.get_status()
    assert retrieved == "Test status message", "The retrieved status should match the updated message."

def test_log_update(caplog):
    # Set the logging level to capture INFO logs from the status_update module.
    caplog.set_level("INFO", logger="status_update")
    status_update.update_status("Logging test message")
    # Check that the log contains the expected status update message.
    assert any("Status updated: Logging test message" in record.message for record in caplog.records), "Log should contain the status update message."