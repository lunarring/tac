import subprocess
import sys

def test_tac_make_help():
    # Invoke the CLI help using the 'make' subcommand.
    result = subprocess.run([sys.executable, "src/tac/cli/main.py", "make", "--help"], capture_output=True, text=True)
    output = result.stdout
    # Check that the help text includes the 'make' subcommand to confirm renaming
    assert "make" in output, "The 'make' subcommand is not present in the help output."