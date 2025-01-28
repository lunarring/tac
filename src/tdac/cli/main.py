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

from tdac.protoblock import ProtoBlock, validate_protoblock_json, save_protoblock, ProtoBlockFactory
from tdac.agents.aider_agent import AiderAgent
from tdac.core.executor import ProtoBlockExecutor
from tdac.core.log_config import setup_logger
from tdac.utils.file_gatherer import gather_python_files
from tdac.utils.file_summarizer import FileSummarizer
from tdac.core.llm import LLMClient, Message
from tdac.core.git_manager import GitManager
from tdac.utils.project_files import ProjectFiles

logger = setup_logger(__name__)

def load_config():
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'config.yaml')
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def load_protoblock_from_json(json_path: str) -> ProtoBlock:
    """Load protoblock definition from a JSON file"""
    with open(json_path, 'r') as f:
        data = json.load(f)
    
    # Handle new versioned format
    if isinstance(data, dict) and 'versions' in data:
        # Get the latest version
        version_data = data['versions'][-1]
        block_id = data['block_id']  # Get ID from versioned format
    else:
        # Handle legacy format
        version_data = data
        # Extract block ID from filename as fallback
        filename = os.path.basename(json_path)
        block_id = filename.replace('.tdac_protoblock_', '').replace('.json', '')
    
    task_data = version_data['task']
    test_data = version_data['test']
    
    return ProtoBlock(
        task_description=task_data['specification'],
        test_specification=test_data['specification'],
        test_data_generation=test_data['data'],
        write_files=version_data['write_files'],
        context_files=version_data.get('context_files', []),
        block_id=block_id,
        commit_message=version_data.get('commit_message')
    )

def gather_files_command(args):
    """Handle the gather command execution"""
    if args.summarize:
        project_files = ProjectFiles(args.directory)
        
        # Update summaries and show stats
        exclusions = args.exclusions.split(',') if args.exclusions else None
        stats = project_files.update_summaries(exclusions, not args.include_dot_files)
        
        print(f"\nSummary update stats:")
        print(f"Added: {stats['added']} files")
        print(f"Updated: {stats['updated']} files")
        print(f"Unchanged: {stats['unchanged']} files")
        print(f"Removed: {stats['removed']} files")
        
        # If it's a single file, show its summary
        if os.path.isfile(args.directory) and args.directory.endswith('.py'):
            summary = project_files.get_file_summary(args.directory)
            if summary:
                if "error" in summary:
                    print(f"\nError analyzing file: {summary['error']}")
                else:
                    print(f"\n## File: {os.path.basename(args.directory)}")
                    print(f"Size: {summary['size']} bytes, Last Modified: {summary['last_modified']}")
                    print(f"\n```python\n{summary['summary']}\n```")
        else:
            # Show all summaries
            data = project_files.get_all_summaries()
            print(f"\nLast updated: {data['last_updated']}\n")
            
            for file_path, info in sorted(data["files"].items()):
                if "error" in info:
                    print(f"## File: {file_path}")
                    print(f"Size: {info['size']} bytes, Last Modified: {info['last_modified']}")
                    print(f"Error: {info['error']}\n")
                else:
                    print(f"## File: {file_path}")
                    print(f"Size: {info['size']} bytes, Last Modified: {info['last_modified']}")
                    print(f"\n```python\n{info['summary']}\n```\n")
    else:
        formatting_options = {
            "header": args.header,
            "separator": args.separator,
            "use_code_fences": args.code_fences
        }
        if os.path.isfile(args.directory) and args.directory.endswith('.py'):
            # Single file content
            with open(args.directory, 'r') as f:
                content = f.read()
            file_size = os.path.getsize(args.directory)
            file_info = f"Size: {file_size} bytes, Last Modified: {datetime.fromtimestamp(os.path.getmtime(args.directory))}"
            if formatting_options["use_code_fences"]:
                content = f"```python\n{content}\n```"
            print(f"{formatting_options['header']}{os.path.basename(args.directory)}\n{file_info}\n{content}")
        else:
            # Directory content
            if not os.path.isdir(args.directory):
                print(f"Error: {args.directory} is not a directory or Python file")
                sys.exit(1)
            exclusions = args.exclusions.split(',') if args.exclusions else None
            result = gather_python_files(args.directory, formatting_options, exclusions)
            print(result)

def run_tests_command(args):
    """Handle the test run command"""
    test_dir = args.directory
    if not os.path.exists(test_dir):
        logger.error(f"Test directory not found: {test_dir}")
        sys.exit(1)
    
    # Create a minimal ProtoBlock instance for running tests
    protoblock = ProtoBlock(
        task_description="",    # Not needed for test running
        test_specification="",  # Not needed for test running
        test_data_generation="", # Not needed for test running
        write_files=[],         # Not needed for test running
        context_files=[],       # Not needed for test running
        block_id=os.path.basename(test_dir)  # Use the test directory name as the ID
    )
    
    # Create executor and run tests
    executor = ProtoBlockExecutor(protoblock=protoblock)
    
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
            
        # Create protoblock using factory
        factory = ProtoBlockFactory()
        
        # Get task instructions from template
        task_instructions = factory.get_task_instructions(template_type=template_type)
        
        # Get codebase content
        codebase = gather_python_files(args.directory)
        
        # Generate complete seed instructions
        seed_instructions = factory.get_seed_instructions(codebase, task_instructions)
        
        # Create protoblock from seed instructions
        protoblock = factory.create_protoblock(seed_instructions)
        
        # Save protoblock to file
        json_file = factory.save_protoblock(protoblock)
        
        print(f"\nCreated protoblock: {json_file}")
        
        if args.execute:
            # Initialize git manager and check status
            git_manager = GitManager()
            if not git_manager.check_status()[0]:  # Only check the status boolean, ignore branch name
                sys.exit(1)
                
            # Load configuration
            config = load_config()
            
            # Load and execute the protoblock
            logger.info("Executing protoblock...")
            protoblock_loaded = load_protoblock_from_json(json_file)
            protoblock_loaded.block_id = protoblock.block_id  # Set the block ID
            executor = ProtoBlockExecutor(protoblock=protoblock_loaded)
            success = executor.execute_block()
            
            if success:
                logger.info("Protoblock executed successfully")
                # Handle git operations after successful execution
                if not git_manager.handle_post_execution(config, protoblock_loaded.commit_message):
                    sys.exit(1)
            else:
                logger.error("Protoblock execution failed")
                sys.exit(1)
        else:
            # Just print the protoblock details
            print(f"Generated ProtoBlock (ID: {protoblock.block_id}):")
            print(f"Task: {protoblock.task_specification}")
            print(f"Test Specification: {protoblock.test_specification}")
            print(f"Files to Write: {', '.join(protoblock.write_files)}")
            print(f"Context Files: {', '.join(protoblock.context_files)}")
            print(f"Commit Message: {protoblock.commit_message}")
            
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
    
    # Block command
    block_parser = subparsers.add_parser('block',
        help='Generate and execute a new block with automated tests or custom instructions'
    )
    block_parser.add_argument(
        'directory',
        help='Directory to analyze and create block from'
    )
    block_parser.add_argument(
        '--max-retries',
        type=int,
        help='Override the maximum number of retries (default from config.yaml)'
    )
    block_parser.add_argument(
        '--test',
        nargs='?',
        const='',
        metavar='INSTRUCTIONS',
        help='Generate a test-focused block, optionally with specific test instructions'
    )
    block_parser.add_argument(
        '--refactor',
        nargs='?',
        const='',
        metavar='INSTRUCTIONS',
        help='Generate a refactoring-focused block, optionally with specific refactor instructions'
    )
    block_parser.add_argument(
        '--error',
        nargs='?',
        const='',
        metavar='INSTRUCTIONS',
        help='Generate an error analysis block, optionally with specific error instructions'
    )
    block_parser.add_argument(
        '--instructions',
        type=str,
        help='Generate a custom block with specific instructions'
    )
    block_parser.add_argument(
        '--json',
        type=str,
        help='Path to a JSON file containing a protoblock definition to execute'
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
        '--summarize',
        action='store_true',
        help='Generate detailed summaries of code structure instead of showing file contents'
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
    gather_parser.add_argument(
        '--include-dot-files',
        action='store_true',
        help='Include files and directories that start with a dot'
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
    
    # View command
    view_parser = subparsers.add_parser('view',
        help='Interactive viewer for logs and protoblocks'
    )
    
    args = parser.parse_args()
    
    if args.command == 'block':
        # Count how many template flags are used
        template_flags = sum([
            args.test is not None,
            args.refactor is not None,
            args.error is not None,
            bool(args.instructions),
            bool(args.json)  # Add json flag to template flags
        ])
        
        if template_flags == 0:
            parser.error("Must specify one of: --test, --refactor, --error, --instructions, or --json")
        elif template_flags > 1:
            parser.error("Can only use one of: --test, --refactor, --error, --instructions, or --json")
    
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
        
    if args.command == 'view':
        from tdac.cli.viewer import TDACViewer
        try:
            TDACViewer().main_menu()
        except KeyboardInterrupt:
            print("\nGoodbye!")
            sys.exit(0)
        return

    if args.command == 'block':
        # Initialize git manager and check status
        git_manager = GitManager()
        if not git_manager.check_status()[0]:  # Only check the status boolean, ignore branch name
            sys.exit(1)
            
        try:
            # Load configuration
            config = load_config()
            
            # Override config values with command line arguments if provided
            if args.max_retries is not None:
                config['general']['max_retries'] = args.max_retries
            
            if config['general']['type'] != 'aider':
                raise ValueError(f"Unknown agent type: {config['general']['type']}")
            
            if args.json:
                # Execute block from JSON file
                try:
                    protoblock_loaded = load_protoblock_from_json(args.json)
                    executor = ProtoBlockExecutor(protoblock=protoblock_loaded, config=config)
                    success = executor.execute_block()
                    
                    if success:
                        logger.info("Task completed successfully.")
                        # Handle git operations after successful execution
                        if not git_manager.handle_post_execution(config, protoblock_loaded.commit_message):
                            sys.exit(1)
                    else:
                        logger.error("Task execution failed.")
                        sys.exit(1)
                    return
                except Exception as e:
                    logger.error(f"Error loading or executing protoblock from JSON: {e}")
                    sys.exit(1)
            
            # Create block based on command type
            template_type = None
            direct_instructions = None
            if args.test is not None:
                template_type = "test"
                direct_instructions = args.test
            elif args.refactor is not None:
                template_type = "refactor"
                direct_instructions = args.refactor
            elif args.error is not None:
                template_type = "error"
                direct_instructions = args.error
            elif args.instructions:
                direct_instructions = args.instructions
            
            # Create protoblock using factory
            factory = ProtoBlockFactory()
            
            # Get task instructions
            task_instructions = factory.get_task_instructions(
                template_type=template_type,
                direct_instructions=direct_instructions
            )
            
            # Get codebase content
            codebase = gather_python_files(args.directory)
            
            # Generate complete seed instructions
            seed_instructions = factory.get_seed_instructions(codebase, task_instructions)
            
            # Create protoblock from seed instructions
            protoblock = factory.create_protoblock(seed_instructions)
            
            # Save protoblock to file
            json_file = factory.save_protoblock(protoblock)
            
            print(f"\nCreated protoblock: {json_file}")
            
            # Load protoblock from saved file
            protoblock_loaded = load_protoblock_from_json(json_file)
            protoblock_loaded.block_id = protoblock.block_id
            
            # Create executor and run
            executor = ProtoBlockExecutor(protoblock=protoblock_loaded, config=config)
            success = executor.execute_block()
            
            if success:
                logger.info("Task completed successfully.")
                # Handle git operations after successful execution
                if not git_manager.handle_post_execution(config, protoblock_loaded.commit_message):
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

