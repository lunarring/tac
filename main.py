import os
import yaml
from block import Block
from agent import AiderAgent
from executor import BlockExecutor

def load_config():
    config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

if __name__ == "__main__":
    # Define the path to the original project directory
    original_project_dir = '/Users/jjj/git/tmp/block_test'

    # Create the block directly
    block = Block(
        task_description=(
            "CHANGE: Implement a Python function factorial(n) that returns the factorial of a non-negative integer n "
            "or raises a ValueError if n is negative. For n=0, it should return 1; for n>0, it should multiply "
            "all integers from 1 to n."
        ),
        test_specification="""
        We will create two test functions:
        1) test_factorial_positive_cases(): checks n=0 and n=5 return 1 and 120 respectively.
        2) test_factorial_negative_cases(): checks n=-1 raises ValueError.
        """,
        test_data_generation="""
        Positive data: n=0, n=5
        Negative data: n=-1
        """
    )

    # Ensure the original project directory exists
    if not os.path.exists(original_project_dir):
        os.makedirs(original_project_dir)
        with open(os.path.join(original_project_dir, 'main.py'), 'w', encoding='utf-8') as f:
            f.write("def factorial(n):\n    return None  # Placeholder implementation\n")
        with open(os.path.join(original_project_dir, '__init__.py'), 'w', encoding='utf-8') as f:
            pass  # Create an empty __init__.py
        print("Original project initialized with placeholder code.")

    # Load configuration
    config = load_config()
    
    # Initialize the agent based on config
    if config['agents']['programming']['type'] == 'aider':
        agent = AiderAgent(project_dir=original_project_dir)
    else:
        raise ValueError(f"Unknown agent type: {config['agents']['programming']['type']}")

    # Initialize the executor
    executor = BlockExecutor(block=block, agent=agent, project_dir=original_project_dir)

    # Execute the block
    success = executor.execute_block()

    if success:
        print("Block executed and changes applied successfully.")
    else:
        print("Block execution failed. Changes have been discarded.")

