import os
import pytest
from tac.core.test_runner import TestRunner

def test_run_single_file(tmp_path):
    # Create a temporary test file with a simple test
    test_file = tmp_path / "test_temp_single.py"
    test_file.write_text(
        "def test_temp():\n"
        "    assert True\n"
    )
    
    # Instantiate TestRunner and run tests on the single file
    runner = TestRunner()
    success = runner.run_tests(test_path=str(test_file))
    assert success, "TestRunner did not succeed for a single file."
    
    # Check that at least one test passed
    stats = runner.get_test_stats()
    assert stats.get('passed', 0) >= 1, "Expected at least one passed test."

if __name__ == "__main__":
    pytest.main([os.path.abspath(__file__)])
