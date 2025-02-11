import time
import threading
import unittest
from src.tac.cli.voice import VoiceUI

class TestWaitUntilPrompt(unittest.TestCase):
    def test_wait_until_prompt_exits_prompt(self):
        # Create a VoiceUI instance with a dummy prompt
        voice_ui = VoiceUI(prompt_codebase="dummy")
        
        # Run wait_until_prompt in a separate thread
        def run_wait():
            voice_ui.wait_until_prompt()
        
        wait_thread = threading.Thread(target=run_wait)
        wait_thread.start()
        
        # Wait a short time and simulate the prompt being received
        time.sleep(0.2)
        voice_ui.stop_ai_audio = True
        
        # Wait for the thread to finish, with a timeout for determinism
        wait_thread.join(timeout=1.0)
        self.assertFalse(wait_thread.is_alive(), "wait_until_prompt did not exit after stop flag was set")

if __name__ == '__main__':
    unittest.main()
