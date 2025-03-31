import os
import time
import pytest
from tac.agents.trusty.pytest import PytestTestingAgent as TestRunner

@pytest.fixture
def dummy_tests(tmp_path):
    # Create a temporary tests directory with dummy test files.
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    file1 = test_dir / "test_dummy1.py"
    file2 = test_dir / "test_dummy2.py"
    file1.write_text("def test_func1():\n    pass\n")
    file2.write_text("def test_func2():\n    pass\n")
    # Set file2's modification time to 1 hour ago to simulate it being old.
    old_time = time.time() - 3600
    os.utime(str(file2), (old_time, old_time))
    return test_dir


