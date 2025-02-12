import asyncio
from src.tac.cli.voice import VoiceUI

def test_on_user_transcript():
    voice_ui = VoiceUI()
    test_input = "This is a test voice input"
    asyncio.run(voice_ui.on_user_transcript(test_input))
    assert voice_ui.task_instructions == test_input


