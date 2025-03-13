import os
import pytest
from src.tac.utils.filesystem import cleanup_nested_tests

def test_cleanup_nested_tests_moves_file_and_removes_nested_dir(tmp_path, monkeypatch):
    # Create the parent tests directory and nested tests/tests directory
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    nested_tests_dir = tests_dir / "tests"
    nested_tests_dir.mkdir()
    
    # Create a dummy file in the nested tests directory
    dummy_file = nested_tests_dir / "dummy_test.py"
    dummy_content = "def test_dummy(): assert True"
    dummy_file.write_text(dummy_content)
    
    # Also, create an existing file in the parent tests directory to test conflict removal
    existing_file = tests_dir / "dummy_test.py"
    existing_file.write_text("Old content")
    
    # Change the working directory to tmp_path so that 'tests' refers to tmp_path/tests
    monkeypatch.chdir(tmp_path)
    
    # Call the cleanup function
    cleanup_nested_tests()
    
    # Assert that the dummy file is moved to the parent tests directory with correct content
    moved_file = tests_dir / "dummy_test.py"
    assert moved_file.exists()
    assert moved_file.read_text() == dummy_content
    
    # Assert that the nested tests directory is removed
    assert not nested_tests_dir.exists()

def test_cleanup_nested_tests_no_nested_directory(tmp_path, monkeypatch):
    # Create only the parent tests directory without a nested tests/tests directory
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    
    # Change working directory to tmp_path
    monkeypatch.chdir(tmp_path)
    
    # Calling cleanup_nested_tests should not raise an error
    cleanup_nested_tests()
    
    # Validate that the tests directory still exists
    assert tests_dir.exists()