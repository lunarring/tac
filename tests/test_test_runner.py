import pytest
from tac.trusty_agents.pytest import PytestTestingAgent

def test_get_test_functions():
    # Dummy output simulating pytest output with file and function names
    dummy_output = "collected 3 items\n test_example.py::test_first\n test_example.py::test_second\n test_example.py::test_third"
    
    # Initialize PytestTestingAgent and simulate setting the test_functions attribute with unprocessed lines
    runner = PytestTestingAgent()
    runner.test_functions = [line.strip() for line in dummy_output.splitlines() if "::" in line]
    
    # Expected function names extracted from the dummy output
    expected = ["test_first", "test_second", "test_third"]
    assert runner.get_test_functions() == expected
