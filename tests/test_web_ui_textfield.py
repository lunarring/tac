import os
import time
import unittest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

class WebUITextFieldTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Assumes chromedriver is in PATH. Adjust accordingly if needed.
        cls.driver = webdriver.Chrome()
        # Build file URL for index.html (assumes working directory is project root)
        index_path = os.path.abspath(os.path.join("src", "tac", "web", "index.html"))
        cls.file_url = "file://" + index_path
        cls.driver.get(cls.file_url)
        # Wait until the textarea element is available and the websocket is initialized.
        WebDriverWait(cls.driver, 10).until(
            EC.presence_of_element_located((By.ID, "userInput"))
        )
        # Wait for the websocket connection to be available on window.
        WebDriverWait(cls.driver, 10).until(
            lambda d: d.execute_script("return typeof window.socket !== 'undefined';")
        )
        # Override the socket.send method to record sent messages
        cls.driver.execute_script("window.sentMessages = [];")
        cls.driver.execute_script("""
            const origSend = window.socket.send.bind(window.socket);
            window.socket.send = function(msg) {
                window.sentMessages.push(msg);
                return origSend(msg);
            }
        """)

    @classmethod
    def tearDownClass(cls):
        cls.driver.quit()

    def test_textfield_enter_key_sends_message(self):
        test_message = "Hello WebSocket!"
        textarea = self.driver.find_element(By.ID, "userInput")
        textarea.clear()
        textarea.send_keys(test_message)
        # Simulate pressing Enter key
        textarea.send_keys(Keys.ENTER)
        # Wait a short moment to allow the event listener to process
        time.sleep(1)
        sent = self.driver.execute_script("return window.sentMessages;")
        self.assertIn(test_message, sent)

if __name__ == "__main__":
    unittest.main()