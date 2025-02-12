import subprocess
import sys

def test_generate_not_in_help():
    result = subprocess.run(
        [sys.executable, "src/tac/cli/main.py", "test", "--help"],
        capture_output=True,
        text=True,
        check=True
    )
    help_output = result.stdout.lower()
    assert "generate" not in help_output, "The help output should not contain 'generate'"

if __name__ == "__main__":
    test_generate_not_in_help()
    print("Test passed: 'generate' is not in the CLI help output.")
