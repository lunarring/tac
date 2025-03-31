import unittest
import os
from bs4 import BeautifulSoup

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

if __name__ == '__main__':
    unittest.main()