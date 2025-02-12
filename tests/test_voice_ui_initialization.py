import asyncio
from src.tac.cli.voice import VoiceUI

def test_on_user_transcript():
    voice_ui = VoiceUI()
    test_input = "This is a test voice input"
    asyncio.run(voice_ui.on_user_transcript(test_input))
    assert voice_ui.task_instructions == test_input

def test_update_instructions_updates_prompt_codebase():
    voice_ui = VoiceUI()
    placeholder = "There is a lot of code here."
    voice_ui.update_instructions()
    # Verify that the prompt_codebase was replaced with dynamic summary data
    assert voice_ui.prompt_codebase != placeholder, "prompt_codebase should be updated dynamically with file summaries"
