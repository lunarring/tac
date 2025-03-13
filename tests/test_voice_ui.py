import asyncio
import pytest

from src.tac.cli.voice import VoiceUI

@pytest.mark.asyncio
async def test_on_user_transcript():
    voice_ui = VoiceUI()
    # Initially, task_instructions should be None and stop_ai_audio False
    assert voice_ui.task_instructions is None
    assert not voice_ui.stop_ai_audio

    transcript = "Test instruction"
    await voice_ui.on_user_transcript(transcript)
    assert voice_ui.task_instructions == transcript
    assert voice_ui.stop_ai_audio

@pytest.mark.asyncio
async def test_on_ai_audio_complete():
    voice_ui = VoiceUI()
    # Set task_instructions non-None
    voice_ui.task_instructions = "Existing instruction"
    # Initially, stop_ai_audio is False
    voice_ui.stop_ai_audio = False
    await voice_ui.on_ai_audio_complete()
    assert voice_ui.stop_ai_audio