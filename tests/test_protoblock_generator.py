import os
import json
import pytest

from tac.blocks.generator import ProtoBlockGenerator
from tac.blocks.model import ProtoBlock

# Dummy classes and functions for testing

class DummyLLMClient:
    def chat_completion(self, messages):
        # Return a fixed valid JSON response with absolute paths for testing path conversion
        response = {
            "task": "Dummy task description",
            "write_files": [os.path.abspath("tests/test_dummy.py"), os.path.abspath("src/dummy.py")],
            "context_files": [os.path.abspath("src/other.py"), os.path.abspath("src/dummy.py")],
            "commit_message": "Dummy commit message",
            "branch_name": "tac/feature/dummy",
            "trusty_agents": ["pytest", "plausibility"],
            "trusty_agent_prompts": {"pytest": "Pytest agent prompt", "plausibility": "Plausibility agent prompt"}
        }
        return json.dumps(response)
    
    def _clean_code_fences(self, text):
        return text

class DummyProjectFiles:
    def get_codebase_summary(self):
        return "dummy file summary"
    
    def update_summaries(self):
        pass

class DummyTrustyAgentRegistry:
    @staticmethod
    def generate_agent_prompts():
        return {"pytest": "Pytest agent prompt", "plausibility": "Plausibility agent prompt"}
    
    @staticmethod
    def get_trusty_agents_description():
        return {"pytest": "Pytest agent description", "plausibility": "Plausibility agent description", "agent1": "Desc", "agent2": "Desc"}

# Monkeypatch TrustyAgentRegistry in the generator module
import tac.blocks.generator as generator_module
generator_module.TrustyAgentRegistry.generate_agent_prompts = DummyTrustyAgentRegistry.generate_agent_prompts
generator_module.TrustyAgentRegistry.get_trusty_agents_description = DummyTrustyAgentRegistry.get_trusty_agents_description

@pytest.fixture
def generator_instance(monkeypatch):
    gen = ProtoBlockGenerator()
    # Override project_files with a dummy implementation
    gen.project_files = DummyProjectFiles()
    return gen

def test_get_protoblock_genesis_prompt(generator_instance):
    task_instructions = "Test Task Instructions"
    # The codebase argument is ignored since get_codebase_summary is called internally
    prompt = generator_instance.get_protoblock_genesis_prompt("ignored", task_instructions)
    assert isinstance(prompt, str)
    assert "Test Task Instructions" in prompt
    assert "dummy file summary" in prompt
    # Removed dummy_agent expectation from prompt

def test_verify_protoblock_valid_and_invalid(generator_instance):
    # Create a valid JSON protoblock as a string
    valid_data = {
        "task": "Valid task",
        "write_files": ["tests/test_valid.py", "src/valid.py"],
        "context_files": ["src/context.py"],
        "commit_message": "Valid commit",
        "branch_name": "tac/feature/valid-task",
        "trusty_agents": ["agent1"],
        "trusty_agent_prompts": {"agent1": "Prompt for agent1"}
    }
    valid_json = json.dumps(valid_data)
    is_valid, error, data = generator_instance.verify_protoblock(valid_json)
    assert is_valid is True
    assert error == ""
    assert isinstance(data, dict)
    # Test with malformed JSON (invalid json string)
    malformed_json = "invalid json"
    is_valid, error, data = generator_instance.verify_protoblock(malformed_json)
    assert is_valid is False
    assert data is None
    assert "Failed to parse JSON" in error or "Expecting value" in error

