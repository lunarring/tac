import os
import shutil
import pytest
from pathlib import Path
from tac.agents.coding.native_agent import NativeAgent
from tac.utils.file_utils import load_file_contents, format_files_for_prompt

# A minimal dummy ProtoBlock to simulate the real one
class DummyProtoBlock:
    def __init__(self, task_description, write_files, context_files, trusty_agent_prompts=None):
        self.task_description = task_description
        self.write_files = write_files
        self.context_files = context_files
        self.trusty_agent_prompts = trusty_agent_prompts or {}
        # Adding trusty_agents attribute for compatibility (if needed)
        # This attribute is used by the executor, though not by NativeAgent directly.
        self.trusty_agents = []

# A dummy LLM client to stub the chat_completion method with a controlled response.
class DummyLLMClient:
    def __init__(self, response_str):
        self.response_str = response_str
        self.last_messages = None

    def chat_completion(self, messages):
        # Capture messages for inline assertions if needed.
        self.last_messages = messages
        return self.response_str

@pytest.fixture
def temp_dir(tmp_path):
    # fixture to return a temporary directory and cleanup after using it
    orig_dir = os.getcwd()
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(orig_dir)

def test_load_file_contents(temp_dir):
    # Create a write file with content.
    write_file = temp_dir / "write.py"
    content = "print('hello world')"
    write_file.write_text(content)
    # Also specify a non existent write file.
    non_existent = temp_dir / "nonexistent.py"
    
    # Test for a real file.
    files = [str(write_file)]
    contents = load_file_contents(files, "write")
    assert contents[str(write_file)] == content
    
    # Test for a non-existent write file: should return a placeholder.
    files = [str(non_existent)]
    contents = load_file_contents(files, "write")
    placeholder = "# This file is empty at the moment."
    assert contents[str(non_existent)] == placeholder

def test_format_files_for_prompt():
    file_contents = {
        "file1.py": "print('Hello')",
        "dir/file2.py": "def foo(): pass"
    }
    
    # Test for normal write file formatting.
    prompt_str = format_files_for_prompt(file_contents)
    for file_path, content in file_contents.items():
        assert f"###FILE: {file_path}" in prompt_str
        assert content in prompt_str
        assert "###END_FILE" in prompt_str
    
    # Test for context file formatting (should include the do not edit comment).
    prompt_context = format_files_for_prompt(file_contents, is_context=True)
    for file_path in file_contents.keys():
        assert f"###FILE: {file_path}" in prompt_context
        assert "# This file is for context only, please do not edit it" in prompt_context

def test_create_implementation_prompt():
    agent = NativeAgent(cwd=".")
    task_description = "Implement dummy functionality."
    context_section = "context file content"
    write_section = "write file content"
    coding_agent_prompts = {"AgentX": "Follow best practices."}
    
    prompt = agent._create_implementation_prompt(task_description, context_section, write_section, coding_agent_prompts)
    assert "Task Description: " in prompt
    assert task_description in prompt
    assert write_section in prompt
    assert "###FILE:" in prompt
    # Confirm additional guidance was added.
    assert "AgentX guidance: Follow best practices." in prompt

def test_deparse_llm_response():
    agent = NativeAgent(cwd=".")
    # Create a dummy response with two file sections and a note.
    dummy_response = (
        "###FILE: write1.py\n"
        "updated content for write1\n"
        "###END_FILE\n"
        "###FILE: write2.py\n"
        "updated content for write2\n"
        "###END_FILE\n"
        "###NOTE:\n"
        "This is a test note.\n"
        "###END_NOTE\n"
    )
    allowed_files = ["write1.py", "write2.py"]
    updated_files, note = agent._deparse_llm_response(dummy_response, allowed_files)
    
    assert "write1.py" in updated_files
    assert updated_files["write1.py"] == "updated content for write1"
    assert "write2.py" in updated_files
    assert updated_files["write2.py"] == "updated content for write2"
    assert note.strip() == "This is a test note."

if __name__ == "__main__":
    pytest.main()
    