import os
import json
import pytest
import tempfile

from tac.blocks.model import ProtoBlock
from tac.blocks.processor import BlockProcessor

# Dummy generator to simulate protoblock generation
class DummyGenerator:
    def get_protoblock_genesis_prompt(self, codebase, prompt):
        return prompt

    def create_protoblock(self, prompt):
        return ProtoBlock(
            block_id="dummy123",
            task_description=prompt,
            write_files=["file1.py"],
            context_files=["context1.py"],
            commit_message="initial commit",
            branch_name="feature/test",
            trusty_agents=["agent1"],
            trusty_agent_prompts={"agent1": "dummy prompt"}
        )

# Dummy executor to bypass execution in run_loop
class DummyExecutor:
    def execute_block(self, protoblock, idx_attempt):
        # Always return success for testing purposes
        return True, "", "none"

@pytest.fixture
def dummy_block_processor():
    # Provide dummy task instructions and codebase; we don't use them because we'll override generator and executor
    bp = BlockProcessor(task_instructions="Test task instruction", codebase="dummy_codebase")
    bp.generator = DummyGenerator()
    bp.executor = DummyExecutor()
    return bp

def test_create_protoblock_generation(dummy_block_processor):
    # Test that create_protoblock returns a valid protoblock from the dummy generator
    dummy_block_processor.create_protoblock(idx_attempt=0, error_analysis="")
    pb = dummy_block_processor.protoblock
    assert isinstance(pb, ProtoBlock)
    assert pb.block_id == "dummy123"
    assert pb.task_description == "Test task instruction"
    assert pb.write_files == ["file1.py"]
    assert pb.context_files == ["context1.py"]
    assert pb.commit_message == "initial commit"
    assert pb.branch_name == "feature/test"
    assert pb.trusty_agents == ["agent1"]
    assert pb.trusty_agent_prompts == {"agent1": "dummy prompt"}

def test_override_new_protoblock(dummy_block_processor):
    # Create a previous protoblock
    previous_pb = ProtoBlock(
        block_id="prev123",
        task_description="Previous task",
        write_files=["old.py"],
        context_files=["old_context.py"],
        commit_message="prev commit",
        branch_name="prev_branch",
        trusty_agents=["agent_old"],
        trusty_agent_prompts={"agent_old": "old prompt"}
    )
    dummy_block_processor.previous_protoblock = previous_pb

    # Create a new protoblock that initially has different values
    new_pb = ProtoBlock(
        block_id="new456",
        task_description="New task",
        write_files=["new.py"],
        context_files=["new_context.py"],
        commit_message="new commit",
        branch_name="new_branch",
        trusty_agents=["agent_new"],
        trusty_agent_prompts={"agent_new": "new prompt"}
    )

    # Override new protoblock with previous one
    dummy_block_processor.override_new_protoblock_with_previous_protoblock(new_pb)
    # Validate that block_id, branch_name and commit_message have been copied over
    assert new_pb.block_id == previous_pb.block_id
    assert new_pb.branch_name == previous_pb.branch_name
    assert new_pb.commit_message == previous_pb.commit_message
    # Other fields should remain unchanged
    assert new_pb.task_description == "New task"

def test_store_previous_protoblock(dummy_block_processor):
    # Create a protoblock and assign to processor then call store_previous_protoblock
    pb = ProtoBlock(
        block_id="storeTest",
        task_description="Store test task",
        write_files=["a.py"],
        context_files=["b.py"],
        commit_message="commit store",
        branch_name="branch_store",
        trusty_agents=["agent_store"],
        trusty_agent_prompts={"agent_store": "store prompt"}
    )
    dummy_block_processor.protoblock = pb
    dummy_block_processor.store_previous_protoblock()
    assert dummy_block_processor.previous_protoblock == pb

def test_proto_block_to_dict():
    pb = ProtoBlock(
        block_id="dictTest",
        task_description="Dict test task",
        write_files=["dict.py"],
        context_files=["dict_context.py"],
        commit_message="dict commit",
        branch_name="dict_branch",
        trusty_agents=["agent_dict"],
        trusty_agent_prompts={"agent_dict": "dict prompt"}
    )
    d = pb.to_dict()
    expected = {
        "task": {
            "specification": "Dict test task"
        },
        "write_files": ["dict.py"],
        "context_files": ["dict_context.py"],
        "commit_message": "dict commit",
        "branch_name": "dict_branch",
        "block_id": "dictTest",
        "trusty_agents": ["agent_dict"],
        "trusty_agent_prompts": {"agent_dict": "dict prompt"},
        "image_url": None
    }
    assert d == expected

def test_save_load_new_format(tmp_path):
    # Create a ProtoBlock and save it using the new versioned JSON format.
    pb = ProtoBlock(
        block_id="saveLoadTest",
        task_description="Save load test task",
        write_files=["save.py"],
        context_files=["load_context.py"],
        commit_message="save load commit",
        branch_name="save_branch",
        trusty_agents=["agent_save"],
        trusty_agent_prompts={"agent_save": "save prompt"}
    )
    file_path = tmp_path / ".tac_protoblock_saveLoadTest.json"
    # Ensure file does not exist before saving
    if file_path.exists():
        file_path.unlink()
    # Save the protoblock; this will write versioned JSON since file does not exist
    saved_path = pb.save(str(file_path))
    assert os.path.exists(saved_path)
    # Load the protoblock using load method
    loaded_pb = ProtoBlock.load(str(file_path))
    # Validate key fields
    assert loaded_pb.block_id == "saveLoadTest"
    assert loaded_pb.task_description == "Save load test task"
    assert loaded_pb.write_files == [os.path.relpath("save.py")]
    assert loaded_pb.context_files == [os.path.relpath("load_context.py")]
    assert loaded_pb.commit_message == "save load commit"
    assert loaded_pb.branch_name == "save_branch"
    assert loaded_pb.trusty_agents == ["agent_save"]
    assert loaded_pb.trusty_agent_prompts == {"agent_save": "save prompt"}

def test_save_load_legacy_format(tmp_path):
    # Create a legacy format file (without versions) manually
    legacy_data = {
        "task": {"specification": "Legacy task"},
        "write_files": ["legacy.py"],
        "context_files": ["legacy_context.py"],
        "commit_message": "legacy commit",
        "branch_name": "legacy_branch",
        "trusty_agents": ["agent_legacy"],
        "trusty_agent_prompts": {"agent_legacy": "legacy prompt"}
    }
    file_path = tmp_path / ".tac_protoblock_legacyTest.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(legacy_data, f)
    # Load the protoblock using legacy format handling
    loaded_pb = ProtoBlock.load(str(file_path))
    # The block_id is derived from the file name
    expected_block_id = "legacyTest"
    assert loaded_pb.block_id == expected_block_id
    assert loaded_pb.task_description == "Legacy task"
    assert loaded_pb.write_files == ["legacy.py"]
    assert loaded_pb.context_files == ["legacy_context.py"]
    assert loaded_pb.commit_message == "legacy commit"
    assert loaded_pb.branch_name == "legacy_branch"
    assert loaded_pb.trusty_agents == ["agent_legacy"]
    assert loaded_pb.trusty_agent_prompts == {"agent_legacy": "legacy prompt"}

def test_load_invalid_json(tmp_path):
    # Write an invalid JSON file and ensure load raises a ValueError
    file_path = tmp_path / "invalid.json"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("{invalid json")
    with pytest.raises(ValueError):
        ProtoBlock.load(str(file_path))