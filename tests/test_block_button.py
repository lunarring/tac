import os
from bs4 import BeautifulSoup

def test_block_button_exists():
    # Locate the index.html file relative to the test file
    index_path = os.path.join(os.path.dirname(__file__), "../src/tac/web/index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        contents = f.read()
    soup = BeautifulSoup(contents, "html.parser")
    block_button = soup.find(id="blockButton")
    assert block_button is not None, "Block button not found in index.html"
    # Ensure that the block button has a canvas element inside it
    canvas = block_button.find(id="cubeCanvas")
    assert canvas is not None, "Block button does not contain the cube canvas"

def test_mic_button_exists():
    # Locate the index.html file relative to the test file
    index_path = os.path.join(os.path.dirname(__file__), "../src/tac/web/index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        contents = f.read()
    soup = BeautifulSoup(contents, "html.parser")
    mic_button = soup.find(id="micButton")
    assert mic_button is not None, "Microphone button not found in index.html"
    # Ensure that the mic button has content (icon/text)
    assert mic_button.text.strip() != "", "Microphone button text is empty"

def test_buttons_same_class():
    # Ensure both buttons use the common action-button class for consistent dimensions
    index_path = os.path.join(os.path.dirname(__file__), "../src/tac/web/index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        contents = f.read()
    soup = BeautifulSoup(contents, "html.parser")
    block_button = soup.find(id="blockButton")
    mic_button = soup.find(id="micButton")
    assert block_button is not None, "Block button not found in index.html"
    assert mic_button is not None, "Microphone button not found in index.html"
    block_classes = block_button.get("class", [])
    mic_classes = mic_button.get("class", [])
    assert "action-button" in block_classes, "Block button missing 'action-button' class"
    assert "action-button" in mic_classes, "Microphone button missing 'action-button' class"