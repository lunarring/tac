import re

def test_placeholder_overlay_exists():
    """
    This test checks whether the overlay element with the placeholder text exists in index.html
    and verifies that it uses a dynamic placeholder rather than the old static text.
    """
    with open('src/tac/web/index.html', 'r', encoding='utf8') as f:
        content = f.read()
    # Check that the overlay element exists
    assert 'id="placeholderOverlay"' in content, "Overlay element with id 'placeholderOverlay' not found."
    # Ensure that the old static placeholder is removed
    assert "currently generating XYZ" not in content, "Old static placeholder text found in the overlay element."
    # Verify that the placeholder is dynamically set by checking for the generateRandomString call.
    assert "generateRandomString" in content, "Dynamic generation of the placeholder is not implemented."

if __name__ == "__main__":
    test_placeholder_overlay_exists()
    print("Test passed: Placeholder overlay exists and is set dynamically in index.html")