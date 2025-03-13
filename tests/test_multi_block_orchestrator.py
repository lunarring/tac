import json
import pytest
from tac.blocks.orchestrator import MultiBlockOrchestrator, ProtoBlockRecipeResult, ProtoBlockRecipe
from tac.core.config import config

# Dummy LLM client to simulate controlled responses
class DummyLLMClient:
    def __init__(self, response):
        self.response = response

    def chat_completion(self, messages):
        return self.response

# Dummy BlockProcessor for simulating execution of a protoblock recipe
class DummyBlockProcessor:
    def __init__(self, recipe_text, codebase, protoblock=None):
        self.recipe_text = recipe_text
        self.codebase = codebase
        self.protoblock = protoblock

    def run_loop(self):
        return True

# Dummy GitManager to simulate git operations
class DummyGitManager:
    def __init__(self):
        self.current_branch = "master"
        self.commits = []
        self.checkout_calls = []

    def get_current_branch(self):
        return self.current_branch

    def checkout_branch(self, branch_name, create=False):
        self.checkout_calls.append(branch_name)
        # Simulate a successful branch checkout
        self.current_branch = branch_name
        return True

    def commit(self, commit_message):
        self.commits.append(commit_message)

# Dummy ProjectFiles to simulate project file updates
class DummyProjectFiles:
    def __init__(self):
        self.summary = "updated codebase summary"

    def update_summaries(self):
        self.summary = "updated codebase summary"

    def get_codebase_summary(self):
        return self.summary

# Patch for ProjectFiles in MultiBlockOrchestrator.execute
def dummy_get_project_files():
    return DummyProjectFiles()

# Test for a valid LLM response with multiple chunks
def test_chunk_valid_response():
    valid_json_response = (
        "```json\n" +
        json.dumps({
            "strategy": "Test strategy",
            "branch_name": "tac/feature/test-task",
            "chunks": [
                {"title": "Chunk 1", "description": "Do something important."},
                {"title": "Chunk 2", "description": "Do another thing."}
            ],
            "list_of_violated_tests": ["tests/test1.py:testA"]
        }, indent=2) +
        "\n```"
    )
    orchestrator = MultiBlockOrchestrator()
    orchestrator.llm_client = DummyLLMClient(valid_json_response)
    task_instructions = "Implement a new feature"
    codebase = "dummy codebase summary"
    result = orchestrator.chunk(task_instructions, codebase)

    assert isinstance(result, ProtoBlockRecipeResult)
    assert result.branch_name == "tac/feature/test-task"
    assert result.strategy == "Test strategy"
    assert len(result.recipes) == 2
    assert result.recipes[0].title == "Chunk 1"
    # Check that the violated tests are extracted correctly
    assert result.raw_data.get("list_of_violated_tests") == ["tests/test1.py:testA"]

# Test for an invalid LLM response that causes fallback to default result
def test_chunk_invalid_response():
    invalid_response = "This is not valid JSON"
    orchestrator = MultiBlockOrchestrator()
    orchestrator.llm_client = DummyLLMClient(invalid_response)
    task_instructions = "Implement a new feature"
    codebase = "dummy codebase summary"
    result = orchestrator.chunk(task_instructions, codebase)

    # Fallback result should have exactly one recipe
    assert isinstance(result, ProtoBlockRecipeResult)
    assert len(result.recipes) == 1
    # The analysis message indicates fallback
    assert "not chunked" in result.analysis.lower()

# Test execute() when user cancels confirmation (simulate input 'n')
def test_execute_user_confirmation_no(monkeypatch):
    # Set confirmation required
    config.general.confirm_multiblock_execution = True

    # Monkeypatch input to return 'n'
    monkeypatch.setattr("builtins.input", lambda prompt: "n")
    
    # Use a valid response so that the chunking would normally succeed
    valid_json_response = (
        "```json\n" +
        json.dumps({
            "strategy": "Test strategy",
            "branch_name": "tac/feature/test-task",
            "chunks": [
                {"title": "Chunk 1", "description": "Do something important."}
            ],
            "list_of_violated_tests": []
        }, indent=2) +
        "\n```"
    )
    orchestrator = MultiBlockOrchestrator()
    orchestrator.llm_client = DummyLLMClient(valid_json_response)
    task_instructions = "Implement a new feature"
    codebase = "dummy codebase summary"
    
    # execute should cancel and return False due to user input 'n'
    result = orchestrator.execute(task_instructions, codebase)
    assert result is False

# Test execute() when execution proceeds automatically and verifies sequential processing and git operations
def test_execute_user_confirmation_yes(monkeypatch):
    # Set confirmation bypass (automatic execution)
    config.general.confirm_multiblock_execution = False

    valid_json_response = (
        "```json\n" +
        json.dumps({
            "strategy": "Test strategy for execution",
            "branch_name": "tac/feature/test-task",
            "chunks": [
                {"title": "Chunk 1", "description": "Do something important."},
                {"title": "Chunk 2", "description": "Do another thing."}
            ],
            "list_of_violated_tests": []
        }, indent=2) +
        "\n```"
    )
    orchestrator = MultiBlockOrchestrator()
    orchestrator.llm_client = DummyLLMClient(valid_json_response)
    task_instructions = "Implement a new feature"
    codebase = "initial codebase summary"

    # Patch BlockProcessor in the processor module used inside execute
    monkeypatch.setattr("tac.blocks.processor.BlockProcessor", DummyBlockProcessor)
    # Patch ProjectFiles to use our dummy version
    monkeypatch.setattr("tac.blocks.orchestrator.ProjectFiles", lambda: DummyProjectFiles())

    # Create a dummy git manager and pass it to execute
    dummy_git_manager = DummyGitManager()

    result = orchestrator.execute(task_instructions, codebase, git_manager=dummy_git_manager)
    # Check that execution was successful
    assert result is True
    # There should be two commits made, one per chunk
    assert len(dummy_git_manager.commits) == 2
    # Ensure that the branch was switched to the one provided in the response
    assert dummy_git_manager.current_branch == "tac/feature/test-task"

    # Reset the configuration for other tests if needed
    config.general.confirm_multiblock_execution = False
