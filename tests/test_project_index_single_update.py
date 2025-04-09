import asyncio
import pytest
from tac.web.ui import UIManager

@pytest.mark.asyncio
async def test_project_index_single_update(monkeypatch):
    call_count = 0

    # Define a fake refresh_index that increments call_count and returns an empty dict.
    def fake_refresh_index():
        nonlocal call_count
        call_count += 1
        return {}

    # Patch the send_status_message method to a no-op async function.
    async def fake_send_status_message(message):
        return

    # Instantiate UIManager with a test base directory.
    ui_manager = UIManager(base_dir=".")
    
    # Monkey-patch the refresh_index method on the ProjectFiles instance.
    monkeypatch.setattr(ui_manager.project_files, "refresh_index", fake_refresh_index)
    
    # Patch send_status_message to avoid external effects.
    monkeypatch.setattr(ui_manager, "send_status_message", fake_send_status_message)
    
    # Run the background file indexer (which should perform the indexing exactly once).
    await ui_manager._background_file_indexer()
    
    # Assert that refresh_index was indeed called a single time.
    assert call_count == 1

    # Additionally, verify that file_summaries has been set (even though it may be empty).
    assert hasattr(ui_manager, "file_summaries")
    
    # Cleanup: cancel any potential background tasks if needed.
    await ui_manager.cancel_background_tasks()
    
    
if __name__ == "__main__":
    # Allow direct running of the test file
    asyncio.run(test_project_index_single_update(monkeypatch=__import__('pytest').MonkeyPatch()))  