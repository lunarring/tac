import pytest
from tac.cli.voice import VoiceUI

def test_voice_ui_instantiation():
    """Test that VoiceUI can be instantiated without prompt_codebase and has default values."""
    try:
        voice_ui = VoiceUI()
    except TypeError:
        pytest.fail("VoiceUI instantiation raised a TypeError with no arguments")
    # Check that task_instructions is initialized as expected (None by default)
    assert voice_ui.task_instructions is None
