import pytest
from tac.blocks.executor import BlockExecutor
from tac.blocks.model import ProtoBlock

# Dummy classes to substitute dependencies in BlockExecutor

class DummyCodingAgent:
    def run(self, protoblock, previous_analysis):
        # Simulate a successful run.
        pass

class DummyGitManager:
    def get_complete_diff(self):
        return "dummy diff"

class DummyTrustyAgentSuccess:
    def check(self, protoblock, codebase, code_diff):
        # Always succeed
        return (True, "", "")

class DummyTrustyAgentFailure:
    def check(self, protoblock, codebase, code_diff):
        # Always fail
        return (False, "dummy failure analysis", "dummy failure type")

# A dummy ProtoBlock to simulate the real one for BlockExecutor tests.
class DummyProtoBlockForExecutor(ProtoBlock):
    def __init__(self, task_description, trusty_agents):
        self.task_description = task_description
        self.trusty_agents = trusty_agents
        # Other attributes can be empty or minimal.
        self.write_files = []
        self.context_files = []
        self.trusty_agent_prompts = {}

@pytest.fixture
def block_executor_success():
    executor = BlockExecutor()
    # Override dependencies with dummy ones.
    executor.coding_agent = DummyCodingAgent()
    executor.git_manager = DummyGitManager()
    # Setup trusty agents to always succeed.
    executor.trusty_agents = {
        "pytest": DummyTrustyAgentSuccess(),
        "agent1": DummyTrustyAgentSuccess(),
        "plausibility": DummyTrustyAgentSuccess()
    }
    # Dummy codebase can be an empty dict.
    executor.codebase = {}
    return executor

@pytest.fixture
def block_executor_failure():
    executor = BlockExecutor()
    executor.coding_agent = DummyCodingAgent()
    executor.git_manager = DummyGitManager()
    # Setup trusty agents: agent1 will fail.
    executor.trusty_agents = {
        "pytest": DummyTrustyAgentSuccess(),
        "agent1": DummyTrustyAgentFailure(),
        "plausibility": DummyTrustyAgentSuccess()
    }
    executor.codebase = {}
    return executor

def test_block_executor_success(block_executor_success):
    # Create a dummy proto block with trusty_agents ordering.
    # The sorted order will be: ["pytest", ... (others except "plausibility")..., "plausibility"]
    dummy_block = DummyProtoBlockForExecutor(task_description="dummy task", trusty_agents=["pytest", "agent1", "plausibility"])
    # Call execute_block
    success, error_analysis, failure_type = block_executor_success.execute_block(dummy_block, idx_attempt=0)
    assert success is True
    assert error_analysis is None or error_analysis == ""
    assert failure_type == ""

def test_block_executor_failure(block_executor_failure):
    dummy_block = DummyProtoBlockForExecutor(task_description="dummy task", trusty_agents=["pytest", "agent1", "plausibility"])
    success, error_analysis, failure_type = block_executor_failure.execute_block(dummy_block, idx_attempt=0)
    assert success is False
    # Check that the failure analysis and type match the dummy failure agent's output.
    assert error_analysis == "dummy failure analysis"
    assert failure_type == "dummy failure type"

if __name__ == "__main__":
    pytest.main()
    