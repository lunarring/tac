import os
import re
from bs4 import BeautifulSoup

def test_protoblock_overlay_exists():
    # Adjust the path if needed based on project structure.
    file_path = os.path.join("src", "tac", "web", "index.html")
    assert os.path.exists(file_path), "index.html file does not exist"

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    soup = BeautifulSoup(content, "html.parser")
    overlay = soup.find(id="protoblockOverlay")
    assert overlay is not None, "The protoblockOverlay element is missing in index.html"

def test_protoblock_overlay_css_animation():
    file_path = os.path.join("src", "tac", "web", "index.html")
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Check that the overlay CSS contains a transition and transform properties
    style_blocks = re.findall(r"<style[^>]*>(.*?)</style>", content, re.DOTALL)
    found = False
    for block in style_blocks:
        if "#protoblockOverlay" in block:
            if "transition:" in block and "transform:" in block:
                found = True
                break
    assert found, "The CSS animation properties for protoblockOverlay are missing"

def test_protoblock_overlay_position_in_right_panel():
    file_path = os.path.join("src", "tac", "web", "index.html")
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    soup = BeautifulSoup(content, "html.parser")
    right_panel = soup.find(id="rightPanel")
    overlay = soup.find(id="protoblockOverlay")
    assert right_panel is not None, "The rightPanel element is missing."
    assert overlay is not None, "The protoblockOverlay element is missing."
    # Check that the overlay is a descendant of rightPanel
    assert overlay in right_panel.descendants, "protoblockOverlay must be inside the rightPanel element."
    
if __name__ == "__main__":
    test_protoblock_overlay_exists()
    test_protoblock_overlay_css_animation()
    test_protoblock_overlay_position_in_right_panel()
    print("All protoblock overlay tests passed.")
    
# END OF FILE