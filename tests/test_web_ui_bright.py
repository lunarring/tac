import os
import re

def test_white_backgrounds():
    index_path = os.path.join(os.path.dirname(__file__), "../src/tac/web/index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()
    # Check that chatColumn has a white background color
    assert "background-color: #fff" in html, "Chat column background is not white"
    # Check that visualizationColumn explicitly sets a white background color
    viz_pattern = r"#visualizationColumn\s*\{([^}]+)\}"
    match = re.search(viz_pattern, html, re.MULTILINE)
    assert match, "No CSS block for visualizationColumn found"
    style_content = match.group(1)
    assert "background-color: #fff" in style_content, "Visualization column background is not white"

def test_cube_color_and_wireframe():
    index_path = os.path.join(os.path.dirname(__file__), "../src/tac/web/index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()
    # Check that the Three.js material is configured with a black color and wireframe enabled
    material_pattern = r"new THREE\.MeshBasicMaterial\(\s*\{([^}]+)\}\s*\)"
    match = re.search(material_pattern, html, re.DOTALL)
    assert match, "MeshBasicMaterial definition not found"
    material_props = match.group(1)
    assert "color: 0x000000" in material_props, "Cube color is not set to black"
    assert "wireframe: true" in material_props, "Cube material is not set to wireframe"
    
if __name__ == "__main__":
    test_white_backgrounds()
    test_cube_color_and_wireframe()
    print("All tests passed.")