import os
import pytest
from src.tac.core.test_runner import TestRunner

def test_run_single_file_only(tmp_path):
    # Create two dummy test files in temporary directory
    test_file1 = tmp_path / "test_file1.py"
    test_file1.write_text(
        "def test_first():\n"
        "    assert True\n\n"
        "def test_second():\n"
        "    assert 1 == 1\n"
    )
    test_file2 = tmp_path / "test_file2.py"
    test_file2.write_text(
        "def test_third():\n"
        "    assert False\n"
    )
    
    # Run tests only from test_file1
    runner = TestRunner()
    success = runner.run_tests(test_path=str(test_file1))
    assert success, "TestRunner did not succeed for the single file."
    
    stats = runner.get_test_stats()
    # We expect test_file1 to have two tests that pass
    assert stats.get('passed', 0) == 2, "Expected 2 passed tests from test_file1."
    
    test_functions = runner.get_test_functions()
    # Verify that only tests from test_file1 are executed (and not from test_file2)
    assert 'test_first' in test_functions, "test_first not found in executed tests."
    assert 'test_second' in test_functions, "test_second not found in executed tests."
    assert 'test_third' not in test_functions, "test_third should not be executed."
    
if __name__ == "__main__":
    pytest.main([os.path.abspath(__file__)])
