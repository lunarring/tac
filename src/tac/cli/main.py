#!/usr/bin/env python
import os
import sys
import yaml
import argparse
import ast
import logging
import json
from datetime import datetime
import git

# Add the src directory to Python path for local development
src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from tac.protoblock import ProtoBlock, validate_protoblock_json, save_protoblock, ProtoBlockFactory
from tac.agents.aider_agent import AiderAgent
from tac.core.executor import ProtoBlockExecutor
from tac.core.test_runner import TestRunner
from tac.core.log_config import setup_logging
from tac.utils.file_gatherer import gather_python_files
from tac.utils.file_summarizer import FileSummarizer
from tac.core.llm import LLMClient, Message
from tac.core.git_manager import GitManager
from tac.utils.project_files import ProjectFiles
from tac.core.config import config
from tac.protoblock.manager import load_protoblock_from_json
from tac.core.block_runner import BlockRunner

logger = setup_logging('tac.cli.main')

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
    test_path = args.directory
    if not os.path.exists(test_path):
        logger.error(f"Test path not found: {test_path}")
        sys.exit(1)
    
    # Use TestRunner directly for running tests
    test_runner = TestRunner()
    success = test_runner.run_tests(test_path=test_path)
    
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



def parse_args() -> tuple[argparse.ArgumentParser, argparse.Namespace]:
    parser = argparse.ArgumentParser(
        description='Test Chain CLI Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Block command
    run_parser = subparsers.add_parser('make',
        help='Execute a task with automated tests based on instructions'
    )
    run_parser.add_argument(
        'instructions',
        nargs=argparse.REMAINDER,
        help='Instructions for the task to execute. Capture all tokens, including those with special characters.'
    )
    run_parser.add_argument(
        '--dir',
        default='.',
        help='Directory to analyze and create block from (default: current directory)'
    )
    
    # Dynamically add arguments from general config
    general_config = config.general
    for key, value in vars(general_config).items():
        arg_name = f'--{key.replace("_", "-")}'
        arg_type = type(value)
        if arg_type == bool:
            # For boolean flags, create both positive and negative versions
            positive_name = arg_name
            negative_name = f'--no-{key.replace("_", "-")}'
            # Create a mutually exclusive group
            group = run_parser.add_mutually_exclusive_group()
            group.add_argument(
                positive_name,
                action='store_true',
                default=None,  # Don't override config default
                help=f'Enable {key.replace("_", " ").title()} (default: {value})'
            )
            group.add_argument(
                negative_name,
                action='store_false',
                dest=key.replace("-", "_"),
                default=None,  # Don't override config default
                help=f'Disable {key.replace("_", " ").title()} (default: {value})'
            )
        else:
            run_parser.add_argument(
                arg_name,
                type=arg_type,
                default=value,
                help=f'{key.replace("_", " ").title()} (default: {value})'
            )

    run_parser.add_argument(
        '--json',
        type=str,
        help='Path to a JSON file containing a protoblock definition to execute'
    )
    run_parser.add_argument(
        '--no-git',
        action='store_true',
        help='Disable all git operations (branch checks, commits, etc.)'
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
        help='Directory or file path containing tests (default: tests)'
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
    
    
    # View command
    view_parser = subparsers.add_parser('view',
        help='Interactive viewer for logs and protoblocks'
    )
    
    # Voice command
    voice_parser = subparsers.add_parser('voice',
        help='Start the voice interface'
    )
    voice_parser.add_argument(
        '--codebase',
        type=str,
        default="There is a lot of code here.",
        help='Description of the codebase for the voice agent'
    )
    voice_parser.add_argument(
        '--temperature',
        type=float,
        default=0.8,
        help='Temperature for the voice agent responses'
    )
    voice_parser.add_argument(
        '--no-git',
        action='store_true',
        help='Disable all git operations (branch checks, commits, etc.)'
    )
    
    args = parser.parse_args()
    
    if args.command == 'run':
        # Only validate that we have either instructions or a JSON file
        if not args.instructions and not args.json:
            parser.error("Must provide either instructions or --json")
        if args.instructions and args.json:
            parser.error("Cannot provide both instructions and --json")
    
    return parser, args

def main():
    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    parser, args = parse_args()
    logger = logging.getLogger(__name__)
    logger.debug(f"Parsed args: {vars(args)}")
    config.override_with_args(vars(args))
    logger.debug(f"Config after override: {config._config}")
    
    if args.command == 'gather':
        gather_files_command(args)
        return
    
    if args.command == 'test':
        if args.test_command == 'run':
            run_tests_command(args)
        elif args.test_command == 'list':
            list_tests_command(args)
        else:
            parser.error("Please specify a test command (run or list)")
        return
        
    if args.command == 'view':
        from tac.cli.viewer import TACViewer
        try:
            TACViewer().main_menu()
        except KeyboardInterrupt:
            print("\nGoodbye!")
            sys.exit(0)
        return

    voice_ui = None
    if args.command == 'voice':
        from tac.cli.voice import VoiceUI
        try:
            voice_ui = VoiceUI()
            if hasattr(args, 'temperature'):
                voice_ui.temperature = args.temperature
            voice_ui.start()
            logger.info(f"Got voice task instructions: {voice_ui.task_instructions}")
            voice_instructions = voice_ui.task_instructions
            
            # Set up all necessary args that make command uses
            # Create a new Namespace with all the make command arguments
            make_args = argparse.Namespace()
            # Required arguments
            make_args.dir = '.'
            make_args.no_git = getattr(args, 'no_git', False)
            make_args.json = None
            make_args.instructions = None  # Will be set from voice_instructions later
            
            # Add all config-based arguments with their defaults
            for key in vars(config.general):
                setattr(make_args, key.replace('-', '_'), getattr(config.general, key))
            
            # Merge the new arguments into the existing args namespace
            for attr in vars(make_args):
                setattr(args, attr, getattr(make_args, attr))
            
        except KeyboardInterrupt:
            print("\nGoodbye!")
            sys.exit(0)

    if args.command == 'make' or voice_ui is not None:
        # Initialize git manager and check status only if git is enabled
        git_manager = None
        
        try:
            # Override config values with command line arguments if provided
            config_override = {}
            for key in vars(config.general):
                arg_key = key.replace('-', '_')  # Convert CLI arg format back to config format
                if hasattr(args, arg_key) and getattr(args, arg_key) is not None:
                    config_override[key] = getattr(args, arg_key)
                
            # Add no_git flag to config
            if args.no_git:
                config_override['git'] = {'enabled': False}

            if config.git.enabled:
                git_manager = GitManager()
                if not git_manager.check_status()[0]:  # Only check the status boolean, ignore branch name
                    sys.exit(1)
            else:
                # Check if plausibility test is enabled but git is disabled
                if config.general.plausibility_test:
                    print("\nError: Plausibility test requires git to be enabled.")
                    print("To proceed, either:")
                    print("1. Enable git by removing --no-git flag")
                    print("2. Disable plausibility test using one of these methods:")
                    print("   - Use --plausibility-test false via CLI")
                    sys.exit(1)

            # First of all: run tests, do they all pass
            logger.info("Test Execution Details:")
            logger.info("="*50)
            logger.info(f"Working directory: {os.getcwd()}")
            logger.info(f"Python path: {sys.path}")
            logger.info("="*50)
            test_runner = TestRunner()
            success = test_runner.run_tests()
            if not success:
                logger.error("Initial Tests failed. They need to be fixed before proceeding. Exiting.")
                sys.exit(1)

            # Get codebase content
            codebase = gather_python_files(args.dir)
            # Get task instructions directly from args.instructions or voice_instructions
            if voice_ui is not None:
                task_instructions = voice_ui.wait_until_prompt()
            else:
                task_instructions = " ".join(args.instructions).strip() if isinstance(args.instructions, list) else args.instructions

            block_runner = BlockRunner(task_instructions, codebase, args.json)

            success = block_runner.run_loop()
            
            if success:
                print("\n✅ Task completed successfully!")
                logger.info("Task completed successfully.")
            else:
                print("\n❌ Task execution failed.")
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

