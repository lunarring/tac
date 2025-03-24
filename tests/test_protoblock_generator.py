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

def test_create_protoblock_with_dummy_llm(monkeypatch, generator_instance):
    # Set dummy config values directly on the generator instance if needed.
    # Here we simply monkeypatch the llm_client and update_summaries function.
    generator_instance.llm_client = DummyLLMClient()
    # Ensure update_summaries does nothing
    monkeypatch.setattr(generator_instance.project_files, "update_summaries", lambda: None)
    
    # Monkey-patch config values if they are referenced; simulate using dummy values.
    import tac.core.config as config_module
    config_module.config.general.use_file_summaries = True
    config_module.config.general.max_retries_protoblock_creation = 1

    # Provide a dummy prompt
    dummy_prompt = "dummy prompt for protoblock creation"
    
    protoblock = generator_instance.create_protoblock(dummy_prompt)
    # Check that the returned object is an instance of ProtoBlock
    assert isinstance(protoblock, ProtoBlock)
    # Check that the task_description field is set correctly
    assert "Dummy task description" in protoblock.task_description
    # Check that commit_message and branch_name are set
    assert protoblock.commit_message.startswith("tac: ")
    assert protoblock.branch_name == "tac/feature/dummy"
    
    # Ensure that the write_files paths are relative
    for path in protoblock.write_files:
        assert not os.path.isabs(path)
    # Ensure context_files does not include files that are also in write_files
    for file in protoblock.context_files:
        assert file not in protoblock.write_files
    # Check trusty_agents include pytest and plausibility as per implementation
    assert "pytest" in protoblock.trusty_agents
    assert "plausibility" in protoblock.trusty_agents
    # Verify that dummy_agent is not present in the trusty_agent_prompts and only expected agents remain
    assert set(protoblock.trusty_agent_prompts.keys()) == {"pytest", "plausibility"}
    