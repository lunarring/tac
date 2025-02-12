import unittest
from tac.cli.voice import VoiceUI

class TestVoiceUIImport(unittest.TestCase):
    def test_import_and_instantiation(self):
        try:
            ui = VoiceUI()
        except ImportError as e:
            self.fail("ImportError raised: " + str(e))
        # The default for task_instructions is None.
        self.assertIsNone(ui.task_instructions)

if __name__ == "__main__":
    unittest.main()
