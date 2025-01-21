#!/usr/bin/env python
import os
import sys
import yaml
import argparse
import ast
import logging
import json
from datetime import datetime

# Add the src directory to Python path for local development
src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from tdac.core.block import Block
from tdac.agents.aider_agent import AiderAgent
from tdac.core.executor import BlockExecutor
from tdac.core.log_config import setup_logger
from tdac.utils.file_gatherer import gather_python_files
from tdac.utils.seed_generator import generate_seed
from tdac.core.llm import LLMClient, Message
from tdac.utils.protoblock_manager import validate_protoblock_json, save_protoblock
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

def generate_seed_command(args):
    """Handle the seed generation command"""
    try:
        # Determine template type based on args
        template_type = "default"
        if args.refactor:
            template_type = "refactor"
        elif args.test:
            template_type = "test"
        elif args.error:
            template_type = "error"
            
        seed = generate_seed(args.directory, template_type=template_type)
        seed_data = json.loads(seed)  # Parse the seed to get the unique ID
        
        if args.execute:
            # Initialize git manager and check status
            git_manager = GitManager()
            if not git_manager.check_status():
                sys.exit(1)
                
            # Initialize LLM client
            llm_client = LLMClient()
            
            # Send seed to LLM
            messages = [
                Message(role="system", content="You are a helpful assistant that generates JSON protoblocks for code tasks. Follow the template exactly and ensure the output is valid JSON. Do not use markdown code fences in your response."),
                Message(role="user", content=seed_data["description"])  # Use only the description part
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
                
            # Save JSON to file using the unique ID from seed
            json_file, block_id = save_protoblock(json_content, template_type, seed_data["id"])
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
            print(seed)
            
    except Exception as e:
        logger.error(f"Error generating protoblock: {e}")
        sys.exit(1)

def list_logs_command(args):
    """Handle the log viewing command"""
    # Get all .tdac_log files in current directory
    log_files = sorted(
        [f for f in os.listdir('.') if f.startswith('.tdac_log_')],
        key=lambda x: os.path.getmtime(x),
        reverse=True
    )
    
    if not log_files:
        print("No log files found in current directory.")
        return
        
    # Display files with numbers
    print("\nAvailable log files (ordered by most recent):")
    for i, file in enumerate(log_files, 1):
        mtime = datetime.fromtimestamp(os.path.getmtime(file))
        block_id = file.replace('.tdac_log_', '')
        print(f"{i}. Block {block_id} - Last modified: {mtime.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Get user selection
    while True:
        try:
            choice = input("\nSelect a log file (1-{}) or 'q' to quit: ".format(len(log_files)))
            if choice.lower() == 'q':
                return
                
            idx = int(choice) - 1
            if 0 <= idx < len(log_files):
                selected_file = log_files[idx]
                break
            else:
                print(f"Please enter a number between 1 and {len(log_files)}")
        except ValueError:
            print("Please enter a valid number")
    
    # Read and display the selected log
    try:
        with open(selected_file, 'r') as f:
            log_data = json.load(f)
            
        # Display log information
        print("\n" + "="*50)
        print(f"Log for Block: {selected_file.replace('.tdac_log_', '')}")
        print("="*50)
        
        # Display protoblock info
        if 'protoblock' in log_data:
            proto = log_data['protoblock']
            print("\nProtoblock Information:")
            print(f"Task Description: {proto.get('task_description', 'N/A')}")
            print(f"Test Specification: {proto.get('test_specification', 'N/A')}")
            
        # Display attempts
        if 'attempts' in log_data:
            print(f"\nTotal Attempts: {len(log_data['attempts'])}")
            for i, attempt in enumerate(log_data['attempts'], 1):
                print(f"\nAttempt {i}:")
                print(f"Timestamp: {attempt['timestamp']}")
                print(f"Success: {'✓' if attempt['success'] else '✗'}")
                
                if attempt.get('git_diff'):
                    print("\nGit Diff:")
                    print(attempt['git_diff'])
                    
                if attempt.get('test_results'):
                    print("\nTest Results:")
                    print(attempt['test_results'])
                print("-"*50)
    except Exception as e:
        print(f"Error reading log file: {e}")

def parse_args() -> tuple[argparse.ArgumentParser, argparse.Namespace]:
    parser = argparse.ArgumentParser(
        description='Test Chain CLI Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Run command
    run_parser = subparsers.add_parser('run',
        help='Run a task with test generation or specific instructions'
    )
    run_parser.add_argument(
        'directory',
        help='Directory to analyze'
    )
    run_parser.add_argument(
        '--test',
        action='store_true',
        help='Generate and run tests for the directory'
    )
    run_parser.add_argument(
        '--refactor',
        action='store_true',
        help='Generate and run refactoring tasks'
    )
    run_parser.add_argument(
        '--error',
        action='store_true',
        help='Generate and run error analysis tasks'
    )
    run_parser.add_argument(
        '--instructions',
        type=str,
        help='Specific instructions for the task'
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
    run_test_parser = test_subparsers.add_parser('run',
        help='Run tests found in tests/ subfolder'
    )
    run_test_parser.add_argument(
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
    
    # Log command
    log_parser = subparsers.add_parser('log',
        help='Interactive log viewer'
    )
    
    args = parser.parse_args()
    
    if args.command == 'run':
        # Count how many template flags are used
        template_flags = sum([
            args.test,
            args.refactor,
            args.error,
            bool(args.instructions)
        ])
        
        if template_flags == 0:
            parser.error("Must specify one of: --test, --refactor, --error, or --instructions")
        elif template_flags > 1:
            parser.error("Can only use one of: --test, --refactor, --error, or --instructions")
    
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
        
    if args.command == 'log':
        from tdac.cli.log_viewer import LogViewer
        try:
            LogViewer().main_menu()
        except KeyboardInterrupt:
            print("\nGoodbye!")
            sys.exit(0)
        return

    if args.command == 'run':
        # Initialize git manager and check status
        git_manager = GitManager()
        if not git_manager.check_status():
            sys.exit(1)
            
        try:
            # Load configuration
            config = load_config()
            
            if config['general']['type'] != 'aider':
                raise ValueError(f"Unknown agent type: {config['general']['type']}")
            
            # Create block based on command type
            if args.test:
                # Generate seed for test generation
                from tdac.utils.seed_generator import generate_seed
                seed = generate_seed(args.directory, template_type="test")
                seed_data = json.loads(seed)
                task_desc = seed_data["description"]
            elif args.refactor:
                # Generate seed for refactoring
                from tdac.utils.seed_generator import generate_seed
                seed = generate_seed(args.directory, template_type="refactor")
                seed_data = json.loads(seed)
                task_desc = seed_data["description"]
            elif args.error:
                # Generate seed for error analysis
                from tdac.utils.seed_generator import generate_seed
                seed = generate_seed(args.directory, template_type="error")
                seed_data = json.loads(seed)
                task_desc = seed_data["description"]
            else:
                # Use provided instructions
                task_desc = args.instructions
            
            # Create block
            block = Block(
                task_description=task_desc,
                test_specification="",  # Will be generated by agent
                test_data_generation="",  # Will be generated by agent
                write_files=[],  # Will be determined by agent
                context_files=[]  # Will be determined by agent
            )
            
            # Create executor and run
            executor = BlockExecutor(block=block, config=config)
            success = executor.execute_block()
            
            if success:
                logger.info("Task completed successfully.")
                # Handle git operations after successful execution
                if not git_manager.handle_post_execution(config, block.commit_message):
                    sys.exit(1)
            else:
                logger.error("Task execution failed.")
                sys.exit(1)
                
        except Exception as e:
            logger.error(f"Error during execution: {e}")
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()

