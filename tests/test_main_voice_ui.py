import pytest
from tac.web.ui import UIManager

def test_ui_manager_instantiation():
    """Test that UIManager can be instantiated without arguments and has default values."""
    try:
        ui_manager = UIManager()
    except TypeError:
        pytest.fail("UIManager instantiation raised a TypeError with no arguments")
    # Check that task_instructions is initialized as expected (None by default)
    assert ui_manager.task_instructions is None