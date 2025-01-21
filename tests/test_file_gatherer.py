import os
import pytest
from tdac.utils.file_gatherer import gather_python_files

def create_file(path, content=""):
    with open(path, 'w') as f:
        f.write(content)

def test_single_level_directory(tmp_path):
    # Setup
    dir_path = tmp_path / "single_level"
    dir_path.mkdir()
    create_file(dir_path / "file1.py", 'print("File 1")')
    create_file(dir_path / "file2.py", 'print("File 2")')

    # Execute
    result = gather_python_files(dir_path)

    # Verify
    expected_files = ["file1.py", "file2.py"]
    for file in expected_files:
        assert f"## File: {file}" in result
    assert 'print("File 1")' in result
    assert 'print("File 2")' in result

def test_multi_level_directory(tmp_path):
    # Setup
    dir_path = tmp_path / "multi_level"
    dir_path.mkdir()
    create_file(dir_path / "fileA.py", 'print("File A")')
    subdir = dir_path / "subdir"
    subdir.mkdir()
    create_file(subdir / "fileB.py", 'print("File B")')
    deeper_subdir = subdir / "deeper_subdir"
    deeper_subdir.mkdir()
    create_file(deeper_subdir / "fileC.py", 'print("File C")')

    # Execute
    result = gather_python_files(dir_path)

    # Verify
    expected_files = ["fileA.py", "fileB.py", "fileC.py"]
    for file in expected_files:
        assert f"## File: {file}" in result
    assert 'print("File A")' in result
    assert 'print("File B")' in result
    assert 'print("File C")' in result

def test_no_python_files(tmp_path):
    # Setup
    dir_path = tmp_path / "empty_directory"
    dir_path.mkdir()

    # Execute
    result = gather_python_files(dir_path)

    # Verify
    assert result == "No Python files found."

def test_formatting_options(tmp_path):
    # Setup
    dir_path = tmp_path / "formatting_options"
    dir_path.mkdir()
    create_file(dir_path / "file1.py", 'print("File 1")')

    # Execute
    formatting_options = {"header": "## File: ", "separator": "\n---\n", "use_code_fences": True}
    result = gather_python_files(dir_path, formatting_options=formatting_options)

    # Verify
    assert "## File: file1.py" in result
    assert "\n---\n" in result
    assert "```" in result

def test_directory_exclusions(tmp_path):
    # Setup
    dir_path = tmp_path / "main"
    dir_path.mkdir()
    create_file(dir_path / "main_file.py", 'print("Main File")')
    git_dir = dir_path / ".git"
    git_dir.mkdir()
    create_file(git_dir / "git_file.py", 'print("Git File")')

    # Execute
    result = gather_python_files(dir_path, exclusions=[".git"])

    # Verify
    assert "main_file.py" in result
    assert "git_file.py" not in result
