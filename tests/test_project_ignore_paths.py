import os
import pytest
from pathlib import Path
from tac.utils.file_gatherer import gather_python_files

@pytest.fixture
def temp_python_project(tmp_path):
    # Create an allowed directory with Python files
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()

    # Create a short Python file (size below threshold)
    allowed_short = allowed_dir / "allowed_short.py"
    allowed_short.write_text("print('Hello World')\n")

    # Create a long Python file (size above MAX_FILE_SIZE, which is 102400 bytes)
    allowed_long = allowed_dir / "allowed_long.py"
    # Generate content slightly above threshold (e.g., 102500 bytes)
    long_content = "A" * 102500
    allowed_long.write_text(long_content)

    # Create a dot directory which should be ignored
    dot_dir = tmp_path / ".ignored"
    dot_dir.mkdir()
    ignored_file = dot_dir / "ignored.py"
    ignored_file.write_text("print('This should be ignored')\n")

    # Create a directory that is in the default exclusions (__pycache__)
    pycache_dir = tmp_path / "__pycache__"
    pycache_dir.mkdir()
    pycache_file = pycache_dir / "should_ignore.py"
    pycache_file.write_text("print('Ignore this too')\n")

    return tmp_path

def test_ignore_paths_and_formatting(temp_python_project):
    output = gather_python_files(str(temp_python_project))

    # Validate that the output does not include ignored directories or their files
    assert ".ignored" not in output, "Ignored dot directory should not be in output"
    assert "ignored.py" not in output, "Ignored file should not be in output"
    assert "__pycache__" not in output, "Ignored __pycache__ directory should not be in output"

    # Validate that files from allowed directories are present
    assert "allowed/" in output, "Allowed directory should appear in output"
    assert "allowed_short.py" in output, "Allowed short file should appear in output"
    assert "allowed_long.py" in output, "Allowed long file should appear in output"

    # Validate that file contents are wrapped in code fences
    assert "```python" in output, "File contents should be wrapped in code fences"

    # Validate that the long file content has been truncated (indicated by 'truncated')
    assert "truncated" in output, "Long file should have truncated content indicator"