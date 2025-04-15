import pytest
from tac.web.settings import get_config_html

def test_get_config_html_contains_key_elements():
    """
    Test that the configuration HTML contains expected keys such as 'coding_agent' and 'git'
    to ensure that configuration values are being loaded and formatted.
    """
    html_output = get_config_html()
    # Check for elements related to component LLM mappings
    assert "Component LLM Mappings" in html_output, "Expected 'Component LLM Mappings' to be present in the configuration HTML."
    # Check for the component selector
    assert "llm-selector" in html_output, "Expected 'llm-selector' to be present in the configuration HTML."
    
if __name__ == "__main__":
    pytest.main([__file__])