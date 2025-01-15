import os
import sys
import yaml
import argparse
from block import Block
from agent import AiderAgent
from executor import BlockExecutor

def load_config():
    config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def load_block_from_yaml(yaml_path: str) -> tuple[Block, str]:
    """Load block definition and project directory from a YAML file"""
    with open(yaml_path, 'r') as f:
        data = yaml.safe_load(f)
    
    project_dir = data['project']['project_dir']
    block_data = data['block']
    
    block = Block(
        function_name=block_data['function_name'],
        file_path=block_data['file_path'],
        task_description=block_data['task_description'],
        test_specification=block_data['test_specification'],
        test_data_generation=block_data['test_data_generation']
    )
    
    return block, project_dir

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Execute a coding block defined in a YAML file',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example usage:
  %(prog)s examples/caesar_cipher.yaml
  %(prog)s --dry-run examples/caesar_cipher.yaml
  %(prog)s --test-only examples/caesar_cipher.yaml
        """
    )
    parser.add_argument(
        'yaml_path',
        help='Path to the YAML file containing the block definition'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Load and validate the YAML file without executing the block'
    )
    parser.add_argument(
        '--skip-tests',
        action='store_true',
        help='Skip running tests after implementing the solution'
    )
    parser.add_argument(
        '--test-only',
        action='store_true',
        help='Only run the tests without executing the block'
    )
    
    args = parser.parse_args()
    
    if args.skip_tests and args.test_only:
        parser.error("Cannot use --skip-tests and --test-only together")
    
    return args

if __name__ == "__main__":
    args = parse_args()
    
    try:
        block, project_dir = load_block_from_yaml(args.yaml_path)
    except FileNotFoundError:
        print(f"Error: YAML file not found: {args.yaml_path}")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"Error: Invalid YAML file: {e}")
        sys.exit(1)
    except KeyError as e:
        print(f"Error: Missing required field in YAML file: {e}")
        sys.exit(1)

    if args.dry_run:
        print(f"Successfully loaded block '{block.function_name}' from {args.yaml_path}")
        print(f"Project directory: {project_dir}")
        sys.exit(0)

    # Ensure the project directory exists
    if not os.path.exists(project_dir):
        os.makedirs(project_dir)
        os.makedirs(os.path.join(project_dir, 'tests'), exist_ok=True)
        
        with open(os.path.join(project_dir, block.file_path), 'w', encoding='utf-8') as f:
            f.write(f"def {block.function_name}(text, shift):\n    return None  # Placeholder implementation\n")
        
        # Create __init__.py files
        with open(os.path.join(project_dir, '__init__.py'), 'w', encoding='utf-8') as f:
            pass
        with open(os.path.join(project_dir, 'tests', '__init__.py'), 'w', encoding='utf-8') as f:
            pass
        
        print("Project initialized with placeholder code.")

    try:
        # Load configuration
        config = load_config()
        
        if config['agents']['programming']['type'] != 'aider':
            raise ValueError(f"Unknown agent type: {config['agents']['programming']['type']}")

        # Initialize the executor with block and project_dir
        executor = BlockExecutor(block=block, project_dir=project_dir)

        if args.test_only:
            # Only run tests
            success = executor.run_tests()
            if success:
                print("All tests passed successfully.")
            else:
                print("Tests failed.")
                sys.exit(1)
        else:
            # Execute the block
            success = executor.execute_block()

            if success:
                print("Block executed and changes applied successfully.")
            else:
                print("Block execution failed. Changes have been discarded.")
                sys.exit(1)
    except Exception as e:
        print(f"Error during execution: {e}")
        sys.exit(1)

