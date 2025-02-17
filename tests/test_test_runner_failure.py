import re
import tempfile
import os
from src.tac.core.test_runner import TestRunner

def test_failure_report():
    with tempfile.TemporaryDirectory() as tmpdirname:
        dummy_file = os.path.join(tmpdirname, "test_dummy_failure.py")
        with open(dummy_file, "w", encoding="utf-8") as f:
            f.write("def test_failure():\n    assert False, 'Intentional failure for testing'\n")
        
        # Run tests on the dummy file
        runner = TestRunner()
        runner.run_tests(dummy_file)
        # Get output summary
        output = runner.get_test_results()
        
        # Assert that the output contains an error indicator and reference to the file with a line number
        assert "AssertionError" in output or "Intentional failure for testing" in output, "Failure indicator not found in test results"
        file_line_ref = re.search(r"test_dummy_failure\.py:\d+", output)
        assert file_line_ref, "No reference to the file and line number found in test results"
