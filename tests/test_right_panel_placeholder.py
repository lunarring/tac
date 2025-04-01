import re

def test_placeholder_overlay_exists():
    """
    This test checks whether the overlay element with the placeholder text exists in index.html.
    """
    with open('src/tac/web/index.html', 'r', encoding='utf8') as f:
        content = f.read()
    assert 'id="placeholderOverlay"' in content, "Overlay element with id 'placeholderOverlay' not found."
    assert "currently generating XYZ" in content, "Placeholder text 'currently generating XYZ' not found in the overlay element."

if __name__ == "__main__":
    test_placeholder_overlay_exists()
    print("Test passed: Placeholder overlay exists in index.html")