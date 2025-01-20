#!/usr/bin/env python
import os
import sys
import yaml
import argparse
import ast

# Add the src directory to Python path for local development
src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from tdac.core.block import Block
from tdac.agents.aider_agent import AiderAgent
from tdac.core.executor import BlockExecutor
from tdac.core.logging import logger
from tdac.utils.file_gatherer import gather_python_files
from tdac.utils.protoblock_generator import generate_protoblock

def load_config():
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'config.yaml')
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def load_block_from_yaml(yaml_path: str) -> Block:
    """Load block definition from a YAML file"""
    with open(yaml_path, 'r') as f:
        data = yaml.safe_load(f)
    
    task_data = data['task']
    test_data = data['test']
    
    block = Block(
        task_description=task_data['specification'],
        test_specification=test_data['specification'],
        test_data_generation=test_data['data'],
        write_files=task_data['write_files'],
        context_files=data.get('context_files', [])
    )
    
    return block

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

def run_tests_command(args):
    """Handle the test run command"""
    test_dir = args.directory
    if not os.path.exists(test_dir):
        logger.error(f"Test directory not found: {test_dir}")
        sys.exit(1)
    
    # Create a minimal Block instance just for running tests
    block = Block(
        function_name="dummy",  # Not used for test running
        file_path="dummy.py",   # Not used for test running
        task_description="",    # Not used for test running
        test_specification="",  # Not used for test running
        test_data_generation="" # Not used for test running
    )
    
    # Create executor with current directory as project dir
    executor = BlockExecutor(block=block, project_dir=os.getcwd())
    
    # Run tests and print results
    success = executor.run_tests(test_path=test_dir)
    
    if not success:
        sys.exit(1)

def list_tests_command(args):
    """Handle the test list command"""
    test_dir = args.directory
    if not os.path.exists(test_dir):
        logger.error(f"Test directory not found: {test_dir}")
        sys.exit(1)
    
    def get_test_functions(file_path):
        """Extract test function names from a Python file using ast"""
        with open(file_path, 'r', encoding='utf-8') as f:
            try:
                tree = ast.parse(f.read(), filename=file_path)
            except:
                return []  # Skip files that can't be parsed
        
        return [node.name for node in ast.walk(tree) 
                if isinstance(node, ast.FunctionDef) 
                and (node.name.startswith('test_') or node.name.endswith('_test'))]
    
    test_count = 0
    tests_by_file = {}
    
    # Walk through the test directory
    for root, _, files in os.walk(test_dir):
        for file in files:
            if file.startswith('test_') and file.endswith('.py'):
                file_path = os.path.join(root, file)
                test_functions = get_test_functions(file_path)
                if test_functions:
                    rel_path = os.path.relpath(file_path)
                    tests_by_file[rel_path] = test_functions
                    test_count += len(test_functions)
    
    if not tests_by_file:
        print("\nNo tests found.")
        sys.exit(0)
    
    print("\nAvailable tests:")
    for file_path, tests in sorted(tests_by_file.items()):
        print(f"\n{file_path}:")
        for test in sorted(tests):
            print(f"  - {test}")
    
    print(f"\nTotal tests found: {test_count}")

def generate_tests_command(args):
    """Handle the test generate command"""
    print("\nTest generation feature is coming soon!")
    print("This will help you automatically generate test cases for your functions.")

def generate_protoblock_command(args):
    """Handle the protoblock generation command"""
    try:
        protoblock = generate_protoblock(args.directory)
        print(protoblock)
    except Exception as e:
        logger.error(f"Error generating protoblock: {e}")
        sys.exit(1)

def parse_args() -> tuple[argparse.ArgumentParser, argparse.Namespace]:
    parser = argparse.ArgumentParser(
        description='Test Chain CLI Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Protoblock command
    protoblock_parser = subparsers.add_parser('protoblock',
        help='Generate a protoblock YAML template from a directory'
    )
    protoblock_parser.add_argument(
        'directory',
        help='Directory to generate protoblock from'
    )
    
    # Block execution command
    yaml_parser = subparsers.add_parser('yaml', 
        help='Execute a coding block defined in a YAML file',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example usage:
  %(prog)s examples/caesar_cipher.yaml
  %(prog)s --gen-tests examples/caesar_cipher.yaml
  %(prog)s --gen-task examples/caesar_cipher.yaml
  %(prog)s --run-tests examples/caesar_cipher.yaml
        """
    )
    yaml_parser.add_argument(
        'yaml_path',
        help='Path to the YAML file containing the block definition'
    )
    yaml_parser.add_argument(
        '--gen-tests',
        action='store_true',
        help='Only generate the tests without executing the task'
    )
    yaml_parser.add_argument(
        '--gen-task',
        action='store_true',
        help='Only execute the task without generating tests'
    )
    yaml_parser.add_argument(
        '--run-tests',
        action='store_true',
        help='Only run the tests without generating tests or executing task'
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
    
    # Test command
    test_parser = subparsers.add_parser('test',
        help='Test-related commands'
    )
    test_subparsers = test_parser.add_subparsers(dest='test_command', help='Test commands')
    
    # Run tests command
    run_parser = test_subparsers.add_parser('run',
        help='Run tests found in tests/ subfolder'
    )
    run_parser.add_argument(
        '--directory',
        default='tests',
        help='Directory containing tests (default: tests)'
    )
    
    # List tests command
    list_parser = test_subparsers.add_parser('list',
        help='List available tests'
    )
    list_parser.add_argument(
        '--directory',
        default='tests',
        help='Directory containing tests (default: tests)'
    )
    
    # Generate tests command
    generate_parser = test_subparsers.add_parser('generate',
        help='Generate tests (placeholder)'
    )
    
    args = parser.parse_args()
    
    if args.command == 'yaml' and sum([args.gen_tests, args.gen_task, args.run_tests]) > 1:
        parser.error("Cannot use multiple operation flags together (--gen-tests, --gen-task, --run-tests)")
    
    return parser, args

def main():
    parser, args = parse_args()
    
    if args.command == 'gather':
        gather_files_command(args)
        return
    
    if args.command == 'test':
        if args.test_command == 'run':
            run_tests_command(args)
        elif args.test_command == 'list':
            list_tests_command(args)
        elif args.test_command == 'generate':
            generate_tests_command(args)
        else:
            parser.error("Please specify a test command (run, list, or generate)")
        return
    
    if args.command == 'protoblock':
        generate_protoblock_command(args)
        return

    if args.command == 'yaml':
        try:
            block = load_block_from_yaml(args.yaml_path)
        except FileNotFoundError:
            logger.error(f"YAML file not found: {args.yaml_path}")
            sys.exit(1)
        except yaml.YAMLError as e:
            logger.error(f"Invalid YAML file: {e}")
            sys.exit(1)
        except KeyError as e:
            logger.error(f"Missing required field in YAML file: {e}")
            sys.exit(1)

        # Ensure tests directory exists
        os.makedirs('tests', exist_ok=True)
        with open(os.path.join('tests', '__init__.py'), 'w', encoding='utf-8') as f:
            pass

        try:
            # Load configuration
            config = load_config()
            
            if config['agents']['programming']['type'] != 'aider':
                raise ValueError(f"Unknown agent type: {config['agents']['programming']['type']}")

            # Initialize the executor with block and config
            executor = BlockExecutor(block=block, config=config)

            if args.gen_tests:
                # Only generate tests
                logger.info("Generating tests...")
                executor.agent.generate_tests()
                logger.info("Tests generated successfully.")
            elif args.gen_task:
                # Execute task without generating tests, but with full retry logic
                logger.info("Executing task...")
                success = executor.execute_block(skip_test_generation=True)
                if success:
                    logger.info("Task executed and verified successfully.")
                else:
                    logger.error("Task implementation failed.")
                    sys.exit(1)
            elif args.run_tests:
                # Only run tests
                success = executor.run_tests()
                if success:
                    logger.info("All tests passed successfully.")
                else:
                    logger.error("Tests failed.")
                    sys.exit(1)
            else:
                # Execute the full block (default behavior)
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

