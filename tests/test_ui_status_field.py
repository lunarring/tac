import os
import pytest
from bs4 import BeautifulSoup

def test_status_field_existence():
    # Construct the path to the index.html file
    html_path = os.path.join(os.path.dirname(__file__), "..", "src", "tac", "web", "index.html")
    assert os.path.exists(html_path), "index.html file does not exist at expected location."

    # Read and parse the HTML file
    with open(html_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    # Locate the right panel container
    right_panel = soup.find(id="rightPanel")
    assert right_panel is not None, "Right panel container with id 'rightPanel' not found."

    # Locate the runtime status field within the right panel
    runtime_status = right_panel.find(id="runtimeStatus")
    assert runtime_status is not None, "Runtime status field with id 'runtimeStatus' not found in right panel."

    # Verify that the runtime status field displays the initial text 'status'
    status_text = runtime_status.get_text(strip=True)
    assert status_text == "status", f"Expected runtime status text to be 'status' but found '{status_text}'."
    
if __name__ == "__main__":
    pytest.main()