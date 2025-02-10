import sys
import os
import unittest
import json
import tempfile
import subprocess

class TestMakeCommandExclamation(unittest.TestCase):
    def test_exclamation_in_command(self):
        # Create a minimal valid protoblock JSON file.
        protoblock = {
            "task": {"specification": "dummy task"},
            "test": {"specification": "dummy test", "data": "dummy data"},
            "write_files": [],
            "commit_message": "dummy commit"
        }
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode='w') as tmp_json:
            json.dump(protoblock, tmp_json)
            tmp_json_path = tmp_json.name

        # Build CLI command that includes an exclamation mark in one of its tokens.
        cmd = [sys.executable,
               os.path.join("src", "tac", "cli", "main.py"),
               "make",
               "Test", "command", "with", "exclamation!","mark",
               "--no-git",
               "--json", tmp_json_path]

        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        os.remove(tmp_json_path)
        combined_output = proc.stdout + proc.stderr

        # Ensure that no unrecognized argument error was produced.
        self.assertNotRegex(combined_output, r"unrecognized arguments", "CLI reported unrecognized arguments")
        self.assertEqual(proc.returncode, 0, "Process did not exit cleanly")

if __name__ == "__main__":
    unittest.main()
