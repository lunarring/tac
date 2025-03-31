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
    # Ensure that the block button has some content (icon/text)
    assert block_button.text.strip() != "", "Block button text is empty"