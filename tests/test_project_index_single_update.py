import asyncio
import time
import pytest
from tac.web.ui import UIManager

@pytest.mark.asyncio
async def test_project_index_single_update(monkeypatch):
    call_count = 0
    # List to record status messages with timestamps
    status_messages = []

    # Define a fake refresh_index that simulates a blocking operation.
    def fake_refresh_index():
        nonlocal call_count
        time.sleep(0.5)  # simulate some delay
        call_count += 1
        return {}

    # Fake send_status_message to record messages and their timestamps.
    async def fake_send_status_message(message):
        status_messages.append((time.time(), message))
        return

    ui_manager = UIManager(base_dir=".")
    monkeypatch.setattr(ui_manager.project_files, "refresh_index", fake_refresh_index)
    monkeypatch.setattr(ui_manager, "send_status_message", fake_send_status_message)

    # Record start time and run background indexing concurrently with a simulated chat action.
    start_time = time.time()
    # Simulate a concurrent chat action that sends a status message.
    chat_task = asyncio.create_task(ui_manager.send_status_message("Chat message processed"))
    # Run the background file indexer.
    indexer_task = asyncio.create_task(ui_manager._background_file_indexer())
    await asyncio.gather(indexer_task, chat_task)
    end_time = time.time()
    duration = end_time - start_time

    # Assert that fake_refresh_index was called exactly once.
    assert call_count == 1
    # Assert that the chat message was processed (status_messages should contain it).
    messages = [msg for _, msg in status_messages]
    assert "Chat message processed" in messages
    # Assert that the overall duration is around the delay of the refresh (not additive), ensuring non-blocking behavior.
    assert duration < 0.8  # duration should be close to the slowest task (~0.5s) rather than the sum of delays

    # Verify that file_summaries attribute is set.
    assert hasattr(ui_manager, "file_summaries")

    # Cleanup background tasks if any remain.
    await ui_manager.cancel_background_tasks()
    
    
if __name__ == "__main__":
    asyncio.run(test_project_index_single_update(monkeypatch=__import__('pytest').MonkeyPatch()))