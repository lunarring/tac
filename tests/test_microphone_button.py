import unittest
import os
import asyncio
import io
from bs4 import BeautifulSoup
from contextlib import redirect_stdout
import websockets
from websockets.exceptions import ConnectionClosed

# Import the handle_connection function from the ui module.
# Assuming the project root is in the PYTHONPATH.
from src.tac.web import ui

class DummyWebSocket:
    def __init__(self, messages):
        self.messages = messages
        self.sent_messages = []
        self.recv_called = False

    async def recv(self):
        if not self.recv_called:
            self.recv_called = True
            return self.messages.pop(0)
        else:
            raise ConnectionClosed(1000, "Dummy connection closed")

    async def send(self, message):
        self.sent_messages.append(message)

class TestMicrophoneButton(unittest.TestCase):
    def test_mic_button_present_and_positioned(self):
        # Construct the path to index.html based on the relative location of this file.
        html_file = os.path.join(os.path.dirname(__file__), '..', 'src', 'tac', 'web', 'index.html')
        with open(html_file, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'html.parser')
        mic_button = soup.find(id="micButton")
        self.assertIsNotNone(mic_button, "Mic button not found in the HTML file.")
        style = mic_button.get("style", "")
        self.assertIn("position: absolute", style, "Mic button does not have absolute positioning.")
        self.assertIn("bottom: 10px", style, "Mic button is not positioned at 10px from the bottom.")
        self.assertIn("right: 10px", style, "Mic button is not positioned at 10px from the right.")
    
    def test_mic_click_event_calls_dummy_function(self):
        # Create a dummy websocket that first sends "mic_click" then closes.
        dummy_ws = DummyWebSocket(["mic_click"])
        f = io.StringIO()
        async def run_test():
            # Capture the printed output
            with redirect_stdout(f):
                try:
                    await ui.handle_connection(dummy_ws)
                except ConnectionClosed:
                    pass  # Expected when dummy websocket raises ConnectionClosed
        asyncio.run(run_test())
        output = f.getvalue()
        self.assertIn("recording is starting", output, "Dummy mic click function did not print the expected message.")

if __name__ == '__main__':
    unittest.main()