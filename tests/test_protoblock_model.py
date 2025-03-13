import json
import os
import tempfile
from datetime import datetime

import pytest

from tac.blocks.model import ProtoBlock
import tac.core.config as config_module

@pytest.fixture
def default_trusty_agents(monkeypatch):
    test_default = ['agent1', 'agent2']
    monkeypatch.setattr(config_module.config.general, 'default_trusty_agents', test_default)
    return test_default

def test_post_init_defaults(default_trusty_agents):
    pb = ProtoBlock(
        task_description="Test task",
        write_files=["file1.py"],
        context_files=["file2.py"],
        block_id="test1",
        trusty_agents=None,
        trusty_agent_prompts=None,
        commit_message="Test commit",
        branch_name="main"
    )
    assert pb.trusty_agents == default_trusty_agents
    assert pb.trusty_agent_prompts == {}

def test_to_dict(default_trusty_agents):
    pb = ProtoBlock(
        task_description="Test task",
        write_files=["file1.py"],
        context_files=["file2.py"],
        block_id="test2",
        trusty_agents=["custom_agent"],
        trusty_agent_prompts={"custom_agent": "prompt"},
        commit_message="Test commit",
        branch_name="main"
    )
    pb_dict = pb.to_dict()
    expected = {
        "task": {"specification": "Test task"},
        "write_files": ["file1.py"],
        "context_files": ["file2.py"],
        "commit_message": "Test commit",
        "branch_name": "main",
        "block_id": "test2",
        "trusty_agents": ["custom_agent"],
        "trusty_agent_prompts": {"custom_agent": "prompt"}
    }
    assert pb_dict == expected

def test_save_and_load_new_format(tmp_path, default_trusty_agents):
    pb = ProtoBlock(
        task_description="New format test task",
        write_files=["abs/path/file1.py"],
        context_files=["rel/path/file2.py"],
        block_id="new_format_test",
        trusty_agents=["agentX"],
        trusty_agent_prompts={"agentX": "promptX"},
        commit_message="New format commit",
        branch_name="dev"
    )
    file_path = tmp_path / ".tac_protoblock_new_format_test.json"
    saved_file = pb.save(str(file_path))
    loaded_pb = ProtoBlock.load(saved_file)
    assert loaded_pb.task_description == pb.task_description
    assert loaded_pb.commit_message == pb.commit_message
    assert loaded_pb.branch_name == pb.branch_name
    assert loaded_pb.block_id == pb.block_id
    assert loaded_pb.trusty_agents == pb.trusty_agents
    assert loaded_pb.trusty_agent_prompts == pb.trusty_agent_prompts
    assert loaded_pb.write_files == pb.write_files
    assert loaded_pb.context_files == pb.context_files

def test_save_and_load_legacy_format(tmp_path, default_trusty_agents):
    legacy_data = {
        "task": {"specification": "Legacy test task"},
        "write_files": ["file_legacy.py"],
        "context_files": ["file_context.py"],
        "commit_message": "Legacy commit",
        "branch_name": "legacy",
        "trusty_agents": ["legacy_agent"],
        "trusty_agent_prompts": {"legacy_agent": "legacy prompt"},
        "timestamp": datetime.now().isoformat()
    }
    file_path = tmp_path / ".tac_protoblock_legacy_test.json"
    with open(file_path, 'w') as f:
        json.dump(legacy_data, f)
    loaded_pb = ProtoBlock.load(str(file_path))
    assert loaded_pb.task_description == "Legacy test task"
    assert loaded_pb.write_files == ["file_legacy.py"]
    assert loaded_pb.context_files == ["file_context.py"]
    assert loaded_pb.commit_message == "Legacy commit"
    assert loaded_pb.branch_name == "legacy"
    assert loaded_pb.trusty_agents == ["legacy_agent"]
    assert loaded_pb.trusty_agent_prompts == {"legacy_agent": "legacy prompt"}
    