import os
import time
import pytest
from tac.trusty_agents.pytest import PytestTestingAgent as TestRunner

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

def test_collect_all_tests(dummy_tests):
    tr = TestRunner()
    test_names = tr.collect_all_tests(tests_dir=str(dummy_tests))
    assert "test_func1" in test_names
    assert "test_func2" in test_names
    assert len(test_names) == 2

def test_get_modified_tests(dummy_tests):
    tr = TestRunner()
    # Set baseline to just 1 second ago so only the recently modified file qualifies.
    baseline = time.time() - 1
    modified = tr.get_modified_tests(baseline, tests_dir=str(dummy_tests))
    # Only test_dummy1.py should be considered modified.
    assert "test_func1" in modified
    assert "test_func2" not in modified
