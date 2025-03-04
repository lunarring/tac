#!/usr/bin/env python
import os
import sys
import logging

# Disable all logging at the very start before any other imports
if len(sys.argv) > 1 and sys.argv[1] == 'view':
    logging.getLogger().setLevel(logging.CRITICAL)
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

import yaml
import argparse
import ast
import json
from datetime import datetime
import git

# Add the src directory to Python path for local development
src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from tac.protoblock import ProtoBlock, validate_protoblock_json, save_protoblock, ProtoBlockFactory
from tac.coding_agents.aider import AiderAgent
from tac.core.executor import ProtoBlockExecutor
from tac.core.log_config import setup_logging, reset_execution_context, setup_console_logging
from tac.utils.file_summarizer import FileSummarizer
from tac.core.llm import LLMClient, Message
from tac.core.git_manager import GitManager
from tac.utils.project_files import ProjectFiles
from tac.core.config import config, ConfigManager
from tac.protoblock.manager import load_protoblock_from_json
from tac.core.block_runner import BlockRunner
from tac.testing_agents.pytest import PytestTestingAgent as TestRunner
from tac.core.optimizer import CodeOptimizer

logger = setup_logging('tac.cli.main')

def cli_gather_python_files(directory, formatting_options, exclusions, exclude_dot_files=True):
    """
    Gather Python files from directory and load file contents without extra summarization.
    
    Args:
        directory: Directory to scan.
        formatting_options: Dictionary with formatting options.
        exclusions: List of directories to exclude.
        exclude_dot_files: Whether to exclude files/directories starting with a dot.
        
    Returns:
        str: Formatted output of directory tree and file contents.
    """
    MAX_FILE_SIZE = 100 * 1024  
    CHUNK_SIZE = 40 * 1024

    directory_tree = []
    file_contents = []
    seen_files = set()  # Track unique files by their absolute path

    directory = str(directory)  # Ensure directory is a string
    abs_directory = os.path.abspath(directory)  # Get absolute path of base directory

    for root, dirs, files in os.walk(directory):
        # Exclude specified directories and optionally dot directories
        dirs[:] = [d for d in dirs if d not in exclusions and not (exclude_dot_files and d.startswith('.'))]
        rel_root = os.path.relpath(root, directory)
        level = root.replace(directory, '').count(os.sep)
        indent = ' ' * 4 * level
        # Add the root folder name only if it's not the base directory
        if rel_root == '.':
            directory_tree.append(f"{os.path.basename(root)}/")
        else:
            directory_tree.append(f"{indent}{os.path.basename(root)}/")

        for file in files:
            if file.endswith('.py') and not file.startswith('.#') and not (exclude_dot_files and file.startswith('.')):
                file_path = os.path.join(root, file)
                abs_file_path = os.path.abspath(file_path)
                real_path = os.path.realpath(abs_file_path)  # Resolve any symlinks
                
                # Skip if we've seen this file before (either directly or through a symlink)
                if real_path in seen_files:
                    continue
                
                # Skip if file is outside the target directory
                if not real_path.startswith(abs_directory):
                    continue
                
                seen_files.add(real_path)
                directory_tree.append(f"{indent}    {file}")

                # Gather file info
                file_size = os.path.getsize(file_path)
                file_info = f"Size: {file_size} bytes, Last Modified: {datetime.fromtimestamp(os.path.getmtime(file_path))}"

                # Load file content
                if file_size > MAX_FILE_SIZE:
                    with open(file_path, 'r') as f:
                        content = f.read()
                    content = (
                        f"# First {CHUNK_SIZE//1024}KB of file:\n"
                        f"{content[:CHUNK_SIZE]}\n\n"
                        f"# ... [{(file_size - 2*CHUNK_SIZE)//1024}KB truncated] ...\n\n"
                        f"# Last {CHUNK_SIZE//1024}KB of file:\n"
                        f"{content[-CHUNK_SIZE:]}"
                    )
                else:
                    with open(file_path, 'r') as f:
                        content = f.read()

                # Format content
                header = f"{formatting_options['header']}{os.path.relpath(file_path, directory)}"
                if formatting_options.get('use_code_fences'):
                    content = f"```python\n{content}\n```"
                
                file_contents.append(f"{header}\n{file_info}\n{content}")

    if not file_contents:
        return "No Python files found."

    return "\n".join(directory_tree) + formatting_options['separator'] + "\n".join(file_contents)

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
                    print(f"Size: {summary['size']} bytes, Last Modified: {datetime.fromtimestamp(os.path.getmtime(args.directory))}")
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
            result = cli_gather_python_files(args.directory, formatting_options, exclusions)
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
    
    # Optimize command
    optimize_parser = subparsers.add_parser('optimize',
        help='Optimize a specific function in the codebase'
    )
    optimize_parser.add_argument(
        'function_name',
        help='Name of the function to optimize'
    )
    optimize_parser.add_argument(
        '--no-git',
        action='store_true',
        help='Disable all git operations (branch checks, commits, etc.)'
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
    parser, args = parse_args()
    
    # Initialize config before any logging
    config.override_with_args(vars(args))
    
    # Set up logging with config values
    log_level = config.logging.get_tac('level', 'INFO')
    log_color = config.logging.get_tac('color', 'green')
    global logger
    logger = setup_logging('tac.cli.main', log_level=log_level, log_color=log_color)
    
    # For the 'view' command, don't set up any logging system
    if args.command == 'view':
        # Import and run the viewer without creating log files
        from tac.cli.viewer import TACViewer
        try:
            TACViewer().main_menu()
        except KeyboardInterrupt:
            print("\nGoodbye!")
            sys.exit(0)
        return
    
    # Configure logging for all other commands
    logger.debug(f"Overriding config with args: {vars(args)}")
    logger.debug(f"Config after override: {config}")
    
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
    
    if args.command == 'optimize':
        logger.debug(f"Optimizing function: {args.function_name}")
        optimizer = CodeOptimizer(args.function_name, config)
        optimizer.optimize() 
        print("\nGoodbye!")
        sys.exit(0) # Call the optimize method

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
            project_files = ProjectFiles()
            project_files.update_summaries()
            codebase = project_files.get_codebase_summary()

            
            if config.general.use_orchestrator:
                if voice_ui is not None:
                    raise NotImplementedError("Voice UI is not supported with orchestrator")
                task_instructions = " ".join(args.instructions).strip() if isinstance(args.instructions, list) else args.instructions
                
                
                # Implement orchestrator
                from tac.core.orchestrator import TaskChunker
                
                logger.info("Using orchestrator to chunk task instructions")
                # Instantiate the TaskChunker directly
                task_chunker = TaskChunker()
                chunking_result = task_chunker.chunk(task_instructions, codebase)
                
                # Get the chunks from the result
                chunks = chunking_result.chunks
                
                logger.info(f"Task chunked into {len(chunks)} potential blocks (chunks)")
                
                # Get branch name directly from the result
                branch_name = chunking_result.branch_name
                
                # Get commit messages for each chunk
                commit_messages = chunking_result.get_commit_messages()
                
                # Display the chunked tasks with commit messages
                print("\n🔍 Task Analysis Complete")
                if chunking_result.strategy:
                    print(f"Strategy: {chunking_result.strategy}")
                print(f"The task has been divided into {len(chunks)} parts")
                if branch_name:
                    print(f"🌿 Git Branch: {branch_name}")
                
                # Display violated tests if any
                if hasattr(chunking_result, 'violated_tests') and chunking_result.violated_tests:
                    print("\n⚠️ Tests that may be violated by this chunking:")
                    for test in chunking_result.violated_tests:
                        print(f"  - {test}")
                else:
                    print("\n✅ No tests will be violated by this chunking")
                
                
                # Display chunks with 1-based indexing for user-friendly output
                for i, chunk in enumerate(chunks):
                    # Display chunk with commit message but without branch name
                    print(f"--- Chunk {i+1} ---")
                    # Display the chunk content without title and branch name
                    print(chunk.get_display_content())
                    print(f"📝 Commit: {commit_messages[i]}")
                    print()
                
                # Ask user if they want to proceed with execution
                proceed = input("\nDo you want to proceed with execution? (y/n): ").lower().strip()
                
                if proceed != 'y':
                    print("Execution cancelled by user.")
                    sys.exit(0)
                
                logger.info(f"Using branch name: {branch_name}")
                
                # Switch to branch if git is enabled and branch name is available
                original_branch = None
                if config.git.enabled and branch_name and git_manager:
                    original_branch = git_manager.get_current_branch()
                    print(f"\n🔄 Switching to branch: {branch_name}")
                    if not git_manager.checkout_branch(branch_name, create=True):
                        print(f"Failed to switch to branch {branch_name}, continuing in current branch")
                    
                    # Inform user about commit behavior
                    print("\n📝 Git behavior: Changes will be committed after each chunk but NOT pushed")
                    print("   You can push changes manually after execution completes")
                    print("   You will remain on the feature branch after execution completes")
                
                # Execute each chunk sequentially with 0-based indexing
                success = True
                
                # Disable auto-push for orchestrator mode
                if config.git.enabled:
                    config.override_with_dict({'git': {'auto_push_if_success': False}})
                    logger.info("Auto-push disabled for orchestrator mode (commits will be created but not pushed)")
                
                for i, chunk in enumerate(chunks):
                    print(f"\n🚀 Executing Chunk {i+1}/{len(chunks)}...")

                    # Update codebase if it's not the first chunk
                    if i > 0:
                        project_files.update_summaries()
                        codebase = project_files.get_codebase_summary()
                    
                    # Convert the chunk to text for the BlockRunner
                    chunk_text = chunk.to_text()
                    
                    # Execute the chunk
                    block_runner = BlockRunner(chunk_text, codebase, args.json)
                    chunk_success = block_runner.run_loop()
                    
                    if not chunk_success:
                        print(f"\n❌ Chunk {i+1} execution failed.")
                        success = False
                        break
                    else:
                        print(f"\n✅ Chunk {i+1} completed successfully!")
                        
                        # Create a commit for this chunk if git is enabled
                        if config.git.enabled and git_manager:
                            commit_message = commit_messages[i]
                            print(f"\n📝 Creating commit: {commit_message}")
                            git_manager.commit(commit_message)
                
                # Don't switch back to original branch - stay on feature branch
                # if config.git.enabled and original_branch and git_manager:
                #     print(f"\n🔄 Switching back to branch: {original_branch}")
                #     git_manager.checkout_branch(original_branch)
                
                if success:
                    print("\n✅ Task completed successfully!")
                    print("Each chunk included its own tests, so no additional integration tests are needed.")
                    
                    # Add instructions for pushing changes if git is enabled
                    if config.git.enabled and branch_name and git_manager:
                        print(f"\n📝 Git status: All changes have been committed to branch '{branch_name}'")
                        print(f"   You are now on the feature branch '{branch_name}' with all changes")
                        print(f"   To push changes manually, run: git push origin {branch_name}")
                        print(f"   To switch back to your original branch, run: git checkout {original_branch}")
                    
                    logger.info("Task completed successfully with per-chunk tests.")
                else:
                    print("\n❌ Task execution failed.")
                    logger.error("Task execution failed.")
                    sys.exit(1)
            else:
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