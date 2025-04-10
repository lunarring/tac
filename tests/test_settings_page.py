import pytest
from tac.web.settings import get_config_html

def test_get_config_html_contains_key_elements():
    """
    Test that the configuration HTML contains expected keys such as 'coding_agent' and 'git'
    to ensure that configuration values are being loaded and formatted.
    """
    html_output = get_config_html()
    # Check for elements from the 'general' section (e.g., coding_agent may be included)
    assert "coding_agent" in html_output, "Expected 'coding_agent' to be present in the configuration HTML."
    # Check for the 'git' section label
    assert "git" in html_output.lower(), "Expected 'git' section to be present in the configuration HTML."
    
if __name__ == "__main__":
    pytest.main([__file__])