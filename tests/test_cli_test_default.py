import sys
from tac.cli.main import parse_args

def test_tac_test_default_directory():
    original_argv = sys.argv
    try:
        sys.argv = ["tac", "test"]
        parser, args = parse_args()
        # Verify that the 'directory' attribute is set to '.' by default
        assert hasattr(args, "directory"), "Parsed arguments do not include 'directory'"
        assert args.directory == ".", f"Default directory expected to be '.', got {args.directory}"
    finally:
        sys.argv = original_argv

if __name__ == "__main__":
    test_tac_test_default_directory()
    print("Test passed: 'tac test' without a directory sets directory to '.'")