import pytest
from tac.core.test_runner import ErrorAnalyzer

class DummyProtoBlock:
    block_id = "dummy_id"
    task_description = "Dummy task"
    test_specification = "Dummy spec"
    test_data_generation = "Dummy data"
    write_files = "dummy_file.py"
    context_files = "None"

def dummy_chat_completion(messages):
    return "Dummy analysis: issue detected"

def test_analyze_failure_dummy(monkeypatch):
    analyzer = ErrorAnalyzer()
    monkeypatch.setattr(analyzer.llm_client, "chat_completion", dummy_chat_completion)
    dummy_codebase = {"dummy_file.py": "print('Hello World')"}
    dummy_test_results = "dummy test results"
    protoblock = DummyProtoBlock()
    
    output = analyzer.analyze_failure(protoblock, dummy_test_results, dummy_codebase)
    assert "Dummy analysis: issue detected" in output
