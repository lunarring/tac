import os
import sys
import yaml
import argparse

# Add the src directory to Python path for local development
src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from test_chain.core.block import Block
from test_chain.agents.aider_agent import AiderAgent
from test_chain.core.executor import BlockExecutor
from test_chain.core.logging import logger
from test_chain.utils.file_gatherer import gather_python_files

def load_config():
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'config.yaml')
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

def gather_files_command(args):
    """Handle the gather command execution"""
    formatting_options = {
        "header": args.header,
        "separator": args.separator,
        "use_code_fences": args.code_fences
    }
    exclusions = args.exclusions.split(',') if args.exclusions else None
    
    result = gather_python_files(args.directory, formatting_options, exclusions)
    print(result)

def parse_args() -> tuple[argparse.ArgumentParser, argparse.Namespace]:
    parser = argparse.ArgumentParser(
        description='Test Chain CLI Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Block execution command
    block_parser = subparsers.add_parser('block', 
        help='Execute a coding block defined in a YAML file',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example usage:
  %(prog)s examples/caesar_cipher.yaml
  %(prog)s --dry-run examples/caesar_cipher.yaml
  %(prog)s --test-only examples/caesar_cipher.yaml
        """
    )
    block_parser.add_argument(
        'yaml_path',
        help='Path to the YAML file containing the block definition'
    )
    block_parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Load and validate the YAML file without executing the block'
    )
    block_parser.add_argument(
        '--skip-tests',
        action='store_true',
        help='Skip running tests after implementing the solution'
    )
    block_parser.add_argument(
        '--test-only',
        action='store_true',
        help='Only run the tests without executing the block'
    )
    
    # File gathering command
    gather_parser = subparsers.add_parser('gather', 
        help='Gather information about Python files in a directory'
    )
    gather_parser.add_argument(
        'directory',
        help='Directory to scan for Python files'
    )
    gather_parser.add_argument(
        '--header',
        default="## File: ",
        help='Header format for each file (default: "## File: ")'
    )
    gather_parser.add_argument(
        '--separator',
        default="\n---\n",
        help='Separator between sections (default: "\\n---\\n")'
    )
    gather_parser.add_argument(
        '--code-fences',
        action='store_true',
        help='Use code fences in output'
    )
    gather_parser.add_argument(
        '--exclusions',
        default=".git,__pycache__",
        help='Comma-separated directories to exclude (default: .git,__pycache__)'
    )
    
    args = parser.parse_args()
    
    if args.command == 'block' and args.skip_tests and args.test_only:
        parser.error("Cannot use --skip-tests and --test-only together")
    
    return parser, args

def main():
    parser, args = parse_args()
    
    if args.command == 'gather':
        gather_files_command(args)
        return
    
    if args.command == 'block':
        try:
            block, project_dir = load_block_from_yaml(args.yaml_path)
        except FileNotFoundError:
            logger.error(f"YAML file not found: {args.yaml_path}")
            sys.exit(1)
        except yaml.YAMLError as e:
            logger.error(f"Invalid YAML file: {e}")
            sys.exit(1)
        except KeyError as e:
            logger.error(f"Missing required field in YAML file: {e}")
            sys.exit(1)

        if args.dry_run:
            logger.info(f"Successfully loaded block '{block.function_name}' from {args.yaml_path}")
            logger.info(f"Project directory: {project_dir}")
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
            
            logger.info("Project initialized with placeholder code.")

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
                    logger.info("All tests passed successfully.")
                else:
                    logger.error("Tests failed.")
                    sys.exit(1)
            else:
                # Execute the block
                success = executor.execute_block()

                if success:
                    logger.info("Block executed and changes applied successfully.")
                else:
                    logger.error("Block execution failed. Changes have been discarded.")
                    sys.exit(1)
        except Exception as e:
            logger.error(f"Error during execution: {e}")
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()

