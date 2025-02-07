import subprocess
import sys
import unittest

class TestCLIGitRemoved(unittest.TestCase):
    def test_git_not_in_help(self):
        # Run the CLI with the '--help' flag and capture output.
        result = subprocess.run([sys.executable, 'src/tac/cli/main.py', '--help'],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, check=True)
        output = result.stdout.lower()
        # Assert that the help output does not include any reference to 'git'
        self.assertNotIn('git', output, "Help output should not contain 'git'")

if __name__ == '__main__':
    unittest.main()
