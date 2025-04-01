import os
import re
import pytest

# Determine the path to the index.html file relative to this test file.
FILE_PATH = os.path.join(os.path.dirname(__file__), "..", "src", "tac", "web", "index.html")

def load_index_html():
    with open(FILE_PATH, "r", encoding="utf-8") as f:
        return f.read()

def test_animation_duration():
    """
    Verify that the typing animation for AI dots runs at double the speed
    by ensuring the animation duration is set to 0.75s and the delays are halved.
    """
    html_content = load_index_html()
    
    # Check the animation duration on the dot class.
    duration_pattern = r"\.dot\s*\{\s*[^}]*animation:\s*typing\s+([0-9.]+)s"
    match = re.search(duration_pattern, html_content, re.MULTILINE)
    assert match, "No animation duration found for .dot elements."
    duration = float(match.group(1))
    assert duration == 0.75, f"Expected animation duration 0.75s, found {duration}s."

def test_animation_delays():
    """
    Verify that the animation delays for the AI dots are correctly updated.
    """
    html_content = load_index_html()
    
    # Check for second dot delay.
    second_dot_pattern = r"\.dot:nth-child\(2\)\s*\{\s*[^}]*animation-delay:\s*([0-9.]+)s"
    match = re.search(second_dot_pattern, html_content, re.MULTILINE)
    assert match, "No animation delay found for .dot:nth-child(2)."
    delay2 = float(match.group(1))
    assert delay2 == 0.15, f"Expected second dot delay 0.15s, found {delay2}s."
    
    # Check for third dot delay.
    third_dot_pattern = r"\.dot:nth-child\(3\)\s*\{\s*[^}]*animation-delay:\s*([0-9.]+)s"
    match = re.search(third_dot_pattern, html_content, re.MULTILINE)
    assert match, "No animation delay found for .dot:nth-child(3)."
    delay3 = float(match.group(1))
    assert delay3 == 0.3, f"Expected third dot delay 0.3s, found {delay3}s."
    
if __name__ == "__main__":
    pytest.main()