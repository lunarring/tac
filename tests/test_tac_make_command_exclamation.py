import subprocess
import sys
import shutil

def test_immediate_verbose_integration():
    """
    Integration test for verifying that CLI immediate verbose mode is active
    when the '--immediate-verbose' flag is provided.
    This test invokes the CLI main script using subprocess, checks that the process
    exits with a 0 exit code, and asserts that the output contains header separators
    indicating immediate verbose logging.
    """
    cmd = [
        sys.executable,
        "src/tac/cli/main.py",
        "--immediate-verbose",
        "test",
        "list",
        "--directory",
        "tests"
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    # Assert process exited with code 0
    assert result.returncode == 0, f"Process exited with {result.returncode}: {result.stderr}"
    # Determine the terminal width and expected separator line
    terminal_width = shutil.get_terminal_size().columns
    separator = "=" * terminal_width
    # Check that the expected separator is found in stdout
    assert separator in result.stdout, "Immediate verbose header separator not found in output."
    
if __name__ == "__main__":
    test_immediate_verbose_integration()
    print("Test passed.")