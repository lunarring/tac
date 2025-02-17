import re
import pytest
from src.tac.core.test_runner import TestRunner

def test_failure_report(tmp_path):
    # Create temporary dummy failing test file within tmp_path
    dummy_file = tmp_path / "test_dummy_failure.py"
    dummy_file.write_text("def test_failure():\n    assert False, 'Intentional failure for testing'\n")
    
    # Run tests on the dummy file
    runner = TestRunner()
    result = runner.run_tests(str(dummy_file))
    # Get output summary
    output = runner.get_test_results()
    
    # Assert the failure message is in the output
    assert "Intentional failure for testing" in output, "Failure message not found in test results"
    
    # Assert that the output references the file with a line number
    file_line_ref = re.search(r"test_dummy_failure\.py:\d+", output)
    assert file_line_ref, "No reference to the file and line number found in test results"
