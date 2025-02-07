import unittest
from src.tac.cli.viewer import TACViewer

class TestTACViewerDummyLogs(unittest.TestCase):
    def test_render_dummy_logs(self):
        dummy_logs = [
            {"timestamp": "2025-02-07 10:00:00", "level": "INFO", "message": "Log entry 1"},
            {"timestamp": "2025-02-07 10:01:00", "level": "ERROR", "message": "Error occurred"}
        ]
        viewer = TACViewer()
        output = viewer.render_dummy_logs(dummy_logs)
        self.assertIn("Log entry 1", output)
        self.assertIn("Error occurred", output)
        self.assertIn("Navigation: use arrow keys", output)
        self.assertIn("Dummy Log Navigation", output)

if __name__ == "__main__":
    unittest.main()
