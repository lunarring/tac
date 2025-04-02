import os
import pytest
import asyncio
from bs4 import BeautifulSoup
from tac.web.ui import UIManager

class DummyWebSocket:
    async def send(self, message):
        # Dummy send method that does nothing
        pass

class DummyAgent:
    def generate_task_instructions(self):
        return "dummy instructions"

@pytest.fixture(scope="function")
def ui_manager(tmp_path, monkeypatch):
    # Set up a temporary directory structure mimicking the project structure for testing
    base_dir = tmp_path
    # Create necessary directories
    web_dir = base_dir / "src" / "tac" / "web"
    web_dir.mkdir(parents=True)
    # Copy content of index.html from original location (simulate minimal content with runtimeStatus)
    index_html_path = web_dir / "index.html"
    index_html_content = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Vibe.tac</title>
</head>
<body>
  <div id="rightPanel">
    <div id="runtimeStatus">status</div>
  </div>
</body>
</html>"""
    index_html_path.write_text(index_html_content, encoding="utf-8")
    
    # Monkeypatch the _get_index_html_path method to use our temporary index.html
    def _get_index_html_path(self):
        return str(index_html_path)
    monkeypatch.setattr(UIManager, "_get_index_html_path", _get_index_html_path)
    
    ui_manager_instance = UIManager(base_dir=str(base_dir))
    return ui_manager_instance

def test_status_field_initial_update(ui_manager):
    # After UIManager initialization, index.html should have runtimeStatus set to 'waiting'
    index_path = ui_manager._get_index_html_path()
    with open(index_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")
    runtime_status = soup.find(id="runtimeStatus")
    assert runtime_status is not None, "Runtime status element not found."
    status_text = runtime_status.get_text(strip=True)
    assert status_text == "waiting", f"Expected runtime status to be 'waiting', but found '{status_text}'."

@pytest.mark.asyncio
async def test_block_click_updates_status(ui_manager):
    # Simulate a block button click
    dummy_ws = DummyWebSocket()
    dummy_agent = DummyAgent()
    await ui_manager.handle_block_click(dummy_ws, dummy_agent)
    
    # After block click, index.html should have runtimeStatus updated to 'creating protoblock'
    index_path = ui_manager._get_index_html_path()
    with open(index_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")
    runtime_status = soup.find(id="runtimeStatus")
    assert runtime_status is not None, "Runtime status element not found after block click."
    status_text = runtime_status.get_text(strip=True)
    assert status_text == "creating protoblock", f"Expected runtime status to be 'creating protoblock', but found '{status_text}'."

if __name__ == "__main__":
    pytest.main()