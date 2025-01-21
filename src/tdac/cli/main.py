#!/usr/bin/env python
import os
import sys
import yaml
import argparse
import ast
import logging
import json

# Add the src directory to Python path for local development
src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from tdac.core.block import Block
from tdac.agents.aider_agent import AiderAgent
from tdac.core.executor import BlockExecutor
from tdac.core.log_config import setup_logger
from tdac.utils.file_gatherer import gather_python_files
from tdac.utils.seedblock_generator import generate_seedblock
from tdac.core.llm import LLMClient, Message
from tdac.utils.json_validator import validate_protoblock_json, save_protoblock
from tdac.core.git_manager import GitManager

logger = setup_logger(__name__)

def load_config():
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'config.yaml')
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def load_block_from_json(json_path: str) -> Block:
    """Load block definition from a JSON file"""
    with open(json_path, 'r') as f:
        data = json.load(f)
    
    task_data = data['task']
    test_data = data['test']
    
    # Extract block ID from filename
    filename = os.path.basename(json_path)
    if filename.startswith('.tdac_protoblock_'):
        # Format is .tdac_protoblock_type_ID.json
        block_id = filename.split('_')[-1].split('.')[0]
    else:
        block_id = None
    
    block = Block(
        task_description=task_data['specification'],
        test_specification=test_data['specification'],
        test_data_generation=test_data['data'],
        write_files=data['write_files'],
        context_files=data.get('context_files', []),
        commit_message=data.get('commit_message')
    )
    
    # Set the block ID if we found one
    if block_id:
        block.block_id = block_id
    
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
    
    # Create a minimal Block instance for running tests
    block = Block(
        task_description="",    # Not needed for test running
        test_specification="",  # Not needed for test running
        test_data_generation="", # Not needed for test running
        write_files=[],         # Not needed for test running
        context_files=[]        # Not needed for test running
    )
    
    # Create executor and run tests
    executor = BlockExecutor(block=block)
    
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

def generate_seedblock_command(args):
    """Handle the seedblock generation command"""
    try:
        # Determine template type based on args
        template_type = "default"
        if args.refactor:
            template_type = "refactor"
        elif args.test:
            template_type = "test"
        elif args.error:
            template_type = "error"
            
        seedblock = generate_seedblock(args.directory, template_type=template_type)
        
        if args.execute:
            # Initialize git manager and check status
            git_manager = GitManager()
            if not git_manager.check_status():
                sys.exit(1)
                
            # Initialize LLM client
            llm_client = LLMClient()
            
            # Send seedblock to LLM
            messages = [
                Message(role="system", content="You are a helpful assistant that generates JSON protoblocks for code tasks. Follow the template exactly and ensure the output is valid JSON. Do not use markdown code fences in your response."),
                Message(role="user", content=seedblock)
            ]
            
            logger.info("Generating protoblock through LLM...")
            response = llm_client.chat_completion(messages)
            json_content = response.choices[0].message.content
            
            # Strip markdown code fences if present
            json_content = json_content.strip()
            if json_content.startswith("```"):
                # Find the first and last code fence
                lines = json_content.split("\n")
                start_idx = next((i for i, line in enumerate(lines) if line.startswith("```")), 0) + 1
                end_idx = next((i for i, line in enumerate(lines[start_idx:], start_idx) if line.startswith("```")), len(lines))
                json_content = "\n".join(lines[start_idx:end_idx]).strip()
            
            # Validate JSON
            is_valid, error = validate_protoblock_json(json_content)
            if not is_valid:
                logger.error(f"Generated JSON is invalid: {error}")
                logger.error("JSON content:")
                print(json_content)
                sys.exit(1)
                
            # Save JSON to file and get block ID
            json_file, block_id = save_protoblock(json_content, template_type)
            abs_json_path = os.path.abspath(json_file)
            
            # Verify file was saved
            if not os.path.exists(abs_json_path):
                logger.error(f"Failed to save protoblock JSON to {abs_json_path}")
                sys.exit(1)
                
            logger.info(f"Saved protoblock to {abs_json_path}")
            logger.info(f"Block ID: {block_id}")
            
            # Print JSON content for inspection
            logger.info("Generated JSON content:")
            print("\n" + json_content + "\n")
            
            # Load configuration
            config = load_config()
            
            # Load and execute the protoblock
            logger.info("Executing protoblock...")
            block = load_block_from_json(json_file)
            block.block_id = block_id  # Set the block ID
            executor = BlockExecutor(block=block)
            success = executor.execute_block()
            
            if success:
                logger.info("Protoblock executed successfully")
                # Handle git operations after successful execution
                if not git_manager.handle_post_execution(config, block.commit_message):
                    sys.exit(1)
            else:
                logger.error("Protoblock execution failed")
                sys.exit(1)
        else:
            print(seedblock)
            
    except Exception as e:
        logger.error(f"Error generating protoblock: {e}")
        sys.exit(1)

def parse_args() -> tuple[argparse.ArgumentParser, argparse.Namespace]:
    parser = argparse.ArgumentParser(
        description='Test Chain CLI Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Seedblock command
    seedblock_parser = subparsers.add_parser('seedblock',
        help='Generate a seedblock JSON template from a directory'
    )
    seedblock_parser.add_argument(
        'directory',
        help='Directory to generate seedblock from'
    )
    seedblock_parser.add_argument(
        '--refactor',
        action='store_true',
        help='Generate a refactoring seedblock template'
    )
    seedblock_parser.add_argument(
        '--test',
        action='store_true',
        help='Generate a testing seedblock template'
    )
    seedblock_parser.add_argument(
        '--error',
        action='store_true',
        help='Generate an error analysis seedblock template'
    )
    seedblock_parser.add_argument(
        '--execute',
        action='store_true',
        help='Process through LLM, save as JSON, and execute the seedblock'
    )
    
    # Block execution command
    json_parser = subparsers.add_parser('json', 
        help='Execute a coding block defined in a JSON file',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example usage:
  %(prog)s examples/caesar_cipher.json
  %(prog)s --gen-tests examples/caesar_cipher.json
  %(prog)s --gen-task examples/caesar_cipher.json
  %(prog)s --run-tests examples/caesar_cipher.json
        """
    )
    json_parser.add_argument(
        'json_path',
        help='Path to the JSON file containing the block definition'
    )
    json_parser.add_argument(
        '--gen-tests',
        action='store_true',
        help='Only generate the tests without executing the task'
    )
    json_parser.add_argument(
        '--gen-task',
        action='store_true',
        help='Only execute the task without generating tests'
    )
    json_parser.add_argument(
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
    
    if args.command == 'json' and sum([args.gen_tests, args.gen_task, args.run_tests]) > 1:
        parser.error("Cannot use multiple operation flags together (--gen-tests, --gen-task, --run-tests)")
    
    return parser, args

def main():
    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
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
    
    if args.command == 'seedblock':
        generate_seedblock_command(args)
        return

    if args.command == 'json':
        # Initialize git manager and check status
        git_manager = GitManager()
        if not git_manager.check_status():
            sys.exit(1)
            
        # Check if existing tests pass
        if os.path.exists('tests'):
            logger.info("Checking if existing tests pass...")
            test_executor = BlockExecutor(block=Block(
                task_description="",    # Not needed for test running
                test_specification="",  # Not needed for test running
                test_data_generation="", # Not needed for test running
                write_files=[],         # Not needed for test running
                context_files=[]        # Not needed for test running
            ))
            if not test_executor.run_tests():
                logger.error("Existing tests are failing. Please fix them before proceeding.")
                sys.exit(1)
            logger.info("All existing tests pass.")
            
        try:
            block = load_block_from_json(args.json_path)
        except FileNotFoundError:
            logger.error(f"JSON file not found: {args.json_path}")
            sys.exit(1)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON file: {e}")
            sys.exit(1)
        except KeyError as e:
            logger.error(f"Missing required field in JSON file: {e}")
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
                    # Handle git operations after successful execution
                    if not git_manager.handle_post_execution(config, block.commit_message):
                        sys.exit(1)
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
                    # Handle git operations after successful execution
                    if not git_manager.handle_post_execution(config, block.commit_message):
                        sys.exit(1)
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

