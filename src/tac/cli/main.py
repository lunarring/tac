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

logger = setup_logging('tac.cli.main')

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
        block_id = filename.replace('.tac_protoblock_', '').replace('.json', '')
    
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
    
    # Use TestRunner directly for running tests
    test_runner = TestRunner()
    success = test_runner.run_tests(test_path=test_dir)
    
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


def parse_args() -> tuple[argparse.ArgumentParser, argparse.Namespace]:
    parser = argparse.ArgumentParser(
        description='Test Chain CLI Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Block command
    run_parser = subparsers.add_parser('run',
        help='Generate and execute a new block with automated tests or custom instructions'
    )
    run_parser.add_argument(
        '--dir',
        default='.',
        help='Directory to analyze and create block from (default: current directory)'
    )
    run_parser.add_argument(
        '--max-retries',
        type=int,
        help='Override the maximum number of retries (default from config.yaml)'
    )
    run_parser.add_argument(
        '--test',
        nargs='?',
        const='',
        metavar='INSTRUCTIONS',
        help='Generate a test-focused block, optionally with specific test instructions'
    )
    run_parser.add_argument(
        '--refactor',
        nargs='?',
        const='',
        metavar='INSTRUCTIONS',
        help='Generate a refactoring-focused block, optionally with specific refactor instructions'
    )
    run_parser.add_argument(
        '--error',
        nargs='?',
        const='',
        metavar='INSTRUCTIONS',
        help='Generate an error analysis block, optionally with specific error instructions'
    )
    run_parser.add_argument(
        '--instructions',
        type=str,
        help='Generate a custom block with specific instructions'
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
    
    git_parser = subparsers.add_parser('git', help='Perform git operations (mergepush, diff, restore)')
    git_subparsers = git_parser.add_subparsers(dest='git_command', help='Git subcommands')
    git_subparsers.add_parser('mergepush', help='Merge the current feature branch into main branch and push to remote')
    git_subparsers.add_parser('diff', help='Show differences between main branch and the current feature branch')
    git_subparsers.add_parser('restore', help='Restore the repository to main branch, discarding changes')
    
    args = parser.parse_args()
    
    if args.command == 'run':
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
        from tac.cli.viewer import TACViewer
        try:
            TACViewer().main_menu()
        except KeyboardInterrupt:
            print("\nGoodbye!")
            sys.exit(0)
        return

    if args.command == 'git':
        git_manager = GitManager()
        if not git_manager.repo:
            print("Not a valid git repository.")
            sys.exit(1)

        if args.git_command == 'mergepush':
            main_branch = 'main'
            current_branch = git_manager.get_current_branch()
            if current_branch in ['main', 'master']:
                print("Already on main branch, nothing to merge.")
            else:
                feature_branch = current_branch
                if not git_manager.checkout_branch(main_branch):
                    print(f"Failed to checkout {main_branch} branch.")
                    sys.exit(1)
                try:
                    git_manager.repo.git.merge(feature_branch)
                    print(f"Successfully merged {feature_branch} into {main_branch}.")
                    # Push changes to remote
                    git_manager.repo.git.push('origin', main_branch)
                    print(f"Successfully pushed changes to remote.")
                    git_manager.repo.git.branch('-d', feature_branch)
                    print(f"Deleted feature branch {feature_branch}.")
                except Exception as e:
                    print(f"Error during merging or pushing: {e}")
                    sys.exit(1)
        elif args.git_command == 'diff':
            main_branch = 'main'
            current_branch = git_manager.get_current_branch()
            if current_branch in ['main', 'master']:
                print("Already on main branch, no differences to show.")
            else:
                try:
                    diff_output = git_manager.repo.git.diff(f"{main_branch}..{current_branch}")
                    if not diff_output:
                        print(f"No differences found between {main_branch} and {current_branch}.")
                    else:
                        print(diff_output)
                except Exception as e:
                    print(f"Error while getting diff: {e}")
                    sys.exit(1)
        elif args.git_command == 'restore':
            main_branch = 'main'
            current_branch = git_manager.get_current_branch()
            if current_branch in ['main', 'master']:
                print("Already on main branch.")
            else:
                if not git_manager.checkout_branch(main_branch):
                    print(f"Failed to checkout {main_branch} branch.")
                    sys.exit(1)
                if git_manager.revert_changes():
                    print(f"Repository restored to {main_branch} branch with a clean working directory.")
                else:
                    print("Failed to clean working directory.")
        else:
            print("Invalid git subcommand. Use 'mergepush', 'diff', or 'restore'.")
        sys.exit(0)

    if args.command == 'run':
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
                
            # Add no_git flag to config
            if args.no_git:
                config['git'] = {'enabled': False}
            elif 'git' not in config:
                config['git'] = {'enabled': True}
            
            if config['general']['type'] != 'aider':
                raise ValueError(f"Unknown agent type: {config['general']['type']}")
            

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

            # Load protoblock from JSON file if provided, otherwise create a new block
            if args.json: 
                protoblock = load_protoblock_from_json(args.json)
                print(f"\n✨ Loaded protoblock: {args.json}")
            else:
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
                
                print(f"\n🔄 Generating protoblock from task instructions: {task_instructions}")
                
                # Generate complete seed instructions
                seed_instructions = factory.get_seed_instructions(codebase, task_instructions)
                
                # Create protoblock from seed instructions
                protoblock = factory.create_protoblock(seed_instructions)
                
                # Save protoblock to file
                json_file = factory.save_protoblock(protoblock)
                print(f"\n✨ Created new protoblock: {json_file}")

            print("\nProtoblock details:")
            print(f"🎯 Task: {protoblock.task_description}")
            print(f"🧪 Test Specification: {protoblock.test_specification}")
            print(f"📝 Files to Write: {', '.join(protoblock.write_files)}")
            print(f"📚 Context Files: {', '.join(protoblock.context_files)}")
            print(f"💬 Commit Message: {protoblock.commit_message}\n")
            print("🚀 Starting protoblock execution...\n")
            
            # Create executor and run with codebase
            executor = ProtoBlockExecutor(
                protoblock=protoblock, 
                config=config,
                codebase=codebase  # Pass codebase to executor
            )
            success = executor.execute_block()
            
            if success:
                print("\n✅ Task completed successfully!")
                logger.info("Task completed successfully.")
                # Handle git operations after successful execution
                if not git_manager.handle_post_execution(config, protoblock.commit_message):
                    sys.exit(1)
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

