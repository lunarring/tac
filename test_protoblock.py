from tac.blocks import ProtoBlock
from tac.core.config import config
import json

# Print the default trusty agents from config
print("Default trusty agents from config:")
print(config.general.default_trusty_agents)

# Test creating a ProtoBlock with default trusty_agents
pb1 = ProtoBlock(
    task_description="Test task",
    test_specification="Test spec",
    test_data_generation="Test data",
    write_files=["file1.py", "file2.py"],
    context_files=["context1.py", "context2.py"],
    block_id="test123"
)

print("\nProtoBlock with default trusty_agents:")
print(f"trusty_agents: {pb1.trusty_agents}")

# Test creating a ProtoBlock with custom trusty_agents
pb2 = ProtoBlock(
    task_description="Test task",
    test_specification="Test spec",
    test_data_generation="Test data",
    write_files=["file1.py", "file2.py"],
    context_files=["context1.py", "context2.py"],
    block_id="test456",
    trusty_agents=["pytest", "linting", "security"]
)

print("\nProtoBlock with custom trusty_agents:")
print(f"trusty_agents: {pb2.trusty_agents}")

# Test saving and loading a ProtoBlock
test_file = "test_protoblock.json"
pb2.save(test_file)
print(f"\nSaved ProtoBlock to {test_file}")

# Load the ProtoBlock from the file
loaded_pb = ProtoBlock.load(test_file)
print("\nLoaded ProtoBlock:")
print(f"trusty_agents: {loaded_pb.trusty_agents}")

# Print the full dictionary representation
print("\nFull dictionary representation:")
print(json.dumps(loaded_pb.to_dict(), indent=2)) 