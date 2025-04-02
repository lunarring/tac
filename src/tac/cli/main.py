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

from tac.blocks import ProtoBlock, ProtoBlockGenerator, BlockExecutor, BlockProcessor, MultiBlockOrchestrator
from tac.agents.coding.aider import AiderAgent
from tac.core.log_config import setup_logging, reset_execution_context, setup_console_logging, update_all_loggers
from tac.utils.file_summarizer import FileSummarizer
from tac.core.llm import LLMClient, Message
from tac.utils.project_files import ProjectFiles
from tac.core.config import config, ConfigManager
from tac.agents.trusty.pytest import PytestTestingAgent as TestRunner
from tac.agents.trusty.performance import PerformanceTestingAgent
from tac.blocks import MultiBlockOrchestrator
from tac.utils.git_manager import create_git_manager

_module_logger = setup_logging('tac.cli.main')

# Define InteractiveBlockProcessor subclass to override the commit logic after verification
class InteractiveBlockProcessor(BlockProcessor):
    def run_loop(self):
        max_retries = config.general.max_retries_block_creation
        _module_logger.info(f"Starting execution loop, using max_retries={max_retries} from config")
        error_analysis = ""
        for idx_attempt in range(max_retries):
            _module_logger.info(f"🔄 Starting block creation and execution attempt {idx_attempt + 1} of {max_retries}", heading=True)
            if idx_attempt > 0:
                if config.general.halt_after_fail:
                    user_input = input("Execution paused after failure. Enter 'r' to revert to last commit (clean state), or 'c' to continue with current state: ").strip().lower()
                    if user_input in ['r', 'revert']:
                        if config.git.enabled:
                            _module_logger.info("Reverting changes as per user selection...")
                            self.git_manager.revert_changes()
                        else:
                            _module_logger.info("Git is disabled; cannot revert changes.")
                    elif user_input in ['c', 'continue']:
                        _module_logger.info("Continuing with current state as per user selection...")
                    else:
                        _module_logger.info("Invalid selection, defaulting to continue without reverting.")
                else:
                    if config.git.enabled:
                        _module_logger.info("Reverting changes while staying on feature branch...")
                        self.git_manager.revert_changes()

            try:
                self.create_protoblock(idx_attempt, error_analysis)
            except ValueError as exc:
                error_analysis = str(exc)
                _module_logger.error(f"Protoblock generation failed on attempt {idx_attempt + 1}: {error_analysis}", heading=True)
                self.store_previous_protoblock()
                continue

            if idx_attempt == 0:
                if not self.handle_git_branch_setup():
                    return False

            execution_success, error_analysis, failure_type = self.executor.execute_block(self.protoblock, idx_attempt)

            if not execution_success:
                _module_logger.error(f"Attempt {idx_attempt + 1} failed. Type: {failure_type}", heading=True)
                if config.general.trusty_agents.run_error_analysis and error_analysis:
                    _module_logger.error(error_analysis)
                self.store_previous_protoblock()
                if not config.general.trusty_agents.run_error_analysis:
                    error_analysis = ""
            else:
                if config.git.enabled:
                    if config.safe_get('general', 'halt_after_verify'):
                        _module_logger.info("Halt after successful verification is enabled.")
                        while True:
                            choice = input("Verification successful! Enter 'c' to commit changes, or 'a' to abort: ").strip().lower()
                            if choice == 'c':
                                commit_success = self.git_manager.handle_post_execution(config.raw_config, self.protoblock.commit_message)
                                if commit_success:
                                    _module_logger.info("Changes committed successfully.")
                                    break
                                else:
                                    _module_logger.error("Failed to commit changes")
                                    return False
                            elif choice == 'a':
                                _module_logger.info("User chose to abort. Reverting changes...")
                                self.git_manager.revert_changes()
                                _module_logger.info("Exiting without committing changes.")
                                break
                            else:
                                _module_logger.info("Invalid selection. Please enter 'c' to commit or 'a' to abort.")
                    else:
                        commit_success = self.git_manager.handle_post_execution(config.raw_config, self.protoblock.commit_message)
                        if not commit_success:
                            _module_logger.error("Failed to commit changes")
                            return False
                return True

        if config.git.enabled and self.protoblock:
            current_branch = self.git_manager.get_current_branch()
            base_branch = self.git_manager.base_branch if self.git_manager.base_branch else "main"
            _module_logger.error("❌ All execution attempts failed", heading=True)
            _module_logger.error("📋 Git Cleanup Commands:")
            _module_logger.error(f"  To switch back to your main branch and clean up:")
            _module_logger.error(f"    git switch {base_branch} && git restore . && git clean -fd && git branch -D {current_branch}")
        return False

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
            result = cli_gather_files(args.directory, formatting_options, exclusions)
            print(result)

def run_tests_command(args):
    """Handle the test run command"""
    logger = setup_logging('tac.cli.main')
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
    logger = setup_logging('tac.cli.main')
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
    # Initialize logger for argument parsing
    logger = setup_logging('tac.cli.main', log_level='DEBUG')
    
    parser = argparse.ArgumentParser(
        description='Test Chain CLI Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--ui', action='store_true', help='Launch a UI server with WebSocket and serve a Three.js Hello World page')
    
    # Add global arguments
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        help='Set the logging level (default: from config)'
    )

    # Dynamically add arguments from general config to main parser
    general_config = config.general
    logger.debug("Adding arguments from general config:")
    for key, value in vars(general_config).items():
        arg_name = f'--{key.replace("_", "-")}'
        arg_type = type(value)
        logger.debug(f"Adding argument: {arg_name} (type: {arg_type})")
        if arg_type == bool:
            # For boolean flags, create both positive and negative versions
            positive_name = arg_name
            negative_name = f'--no-{key.replace("_", "-")}'
            logger.debug(f"Adding boolean arguments: {positive_name} and {negative_name}")
            # Create a mutually exclusive group
            group = parser.add_mutually_exclusive_group()
            group.add_argument(
                positive_name,
                action='store_true',
                default=None,
                dest=key,  # Use the original key as the destination
                help=f'Enable {key.replace("_", " ").title()} (default: {value})'
            )
            group.add_argument(
                negative_name,
                action='store_false',
                dest=key,  # Use the original key as the destination
                default=None,
                help=f'Disable {key.replace("_", " ").title()} (default: {value})'
            )
        else:
            parser.add_argument(
                arg_name,
                type=arg_type,
                default=value,
                dest=key,  # Use the original key as the destination
                help=f'{key.replace("_", " ").title()} (default: {value})'
            )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Block command
    make_parser = subparsers.add_parser('make',
        help='Execute a task with automated tests based on instructions'
    )
    # Also add log-level to the make subcommand to handle both positions
    make_parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        help='Set the logging level (default: from config)'
    )
    make_parser.add_argument(
        'instructions',
        nargs='+',
        help='Instructions for the task to execute. Capture all tokens, including those with special characters.'
    )
    make_parser.add_argument(
        '--dir',
        default='.',
        help='Directory to analyze and create block from (default: current directory)'
    )
    make_parser.add_argument(
        '--image',
        type=str,
        help='Image URL to be associated with the task'
    )
    make_parser.add_argument(
        '--json',
        type=str,
        help='Path to a JSON file containing a protoblock definition to execute'
    )
    make_parser.add_argument(
        '--no-git',
        action='store_true',
        help='Disable all git operations (branch checks, commits, etc.)'
    )
    
    # File gathering command
    gather_parser = subparsers.add_parser('gather',
        help='Gather and analyze Python files in a directory'
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
    gather_parser.add_argument(
        '--format',
        choices=['summary', 'full', 'json'],
        default='summary',
        help='Output format (default: summary)'
    )
    gather_parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        help='Set the logging level (default: from config)'
    )
    
    # Test command
    test_parser = subparsers.add_parser('test',
        help='Run or list tests'
    )
    # Add log-level to the test subcommand
    test_parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        help='Set the logging level (default: from config)'
    )
    test_subparsers = test_parser.add_subparsers(dest='test_command', help='Test commands')
    
    # Run tests command
    run_test_parser = test_subparsers.add_parser('run',
        help='Run tests'
    )
    # Add log-level to the run test subcommand
    run_test_parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        help='Set the logging level (default: from config)'
    )
    run_test_parser.add_argument(
        '--directory',
        default='.',
        help='Directory or file path containing tests (default: current directory)'
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
    # Add log-level to the list test subcommand
    list_parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        help='Set the logging level (default: from config)'
    )
    
    # Optimize command
    optimize_parser = subparsers.add_parser('optimize',
        help='Optimize a Python function'
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
    optimize_parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        help='Set the logging level (default: from config)'
    )
    
    # View command
    view_parser = subparsers.add_parser('view',
        help='View a protoblock in a GUI'
    )
    # Add log-level to the view subcommand
    view_parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        help='Set the logging level (default: from config)'
    )
    
    # Voice command
    voice_parser = subparsers.add_parser('voice',
        help='Start voice interface'
    )
    # Add log-level to the voice subcommand
    voice_parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        help='Set the logging level (default: from config)'
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
    
    # Debug command
    debug_parser = subparsers.add_parser('debug',
        help='Debug commands for development'
    )
    # Add log-level to the debug subcommand
    debug_parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        help='Set the logging level (default: from config)'
    )
    debug_parser.add_argument(
        '--prompt-sections',
        action='store_true',
        help='Print all registered prompt sections'
    )
    
    args = parser.parse_args()
    
    # Set default subcommand for 'test' if none is provided
    if args.command == 'test' and args.test_command is None:
        args.test_command = 'run'
        if not hasattr(args, 'directory') or args.directory is None:
            args.directory = '.'
    
    if args.command == 'make':
        # Only validate that we have either instructions or a JSON file
        if not args.instructions and not args.json:
            parser.error("Must provide either instructions or --json")
        if args.instructions and args.json:
            parser.error("Cannot provide both instructions and --json")
    
    return parser, args

def execute_command(task_instructions=None, protoblock=None, config_overrides=None, ui_manager=None):
    """
    Execute the main command logic that can be triggered from CLI or GUI.
    
    Args:
        task_instructions: Instructions for the task to execute
        protoblock: Optional protoblock object
        config_overrides: Dictionary of config overrides
        ui_manager: Optional UI manager for sending status updates
        
    Returns:
        bool: True if execution was successful, False otherwise
    """
    git_manager = None
    success = False
    logger = _module_logger
    
    try:
        # Apply config overrides if provided
        if config_overrides:
            config.override_with_dict(config_overrides)

        # Handle git settings
        if config.safe_get('general', 'no_git'):
            config.override_with_dict({'git': {'enabled': False}})
            logger.info("Git operations disabled via config")

        git_manager = create_git_manager()
        if not git_manager.check_status()[0]:
            if ui_manager:
                ui_manager.send_status_bar("❌ Git status check failed")
            return False

        logger.info("Test Execution Details:", heading=True)
        logger.info(f"Working directory: {os.getcwd()}")
        logger.info(f"Python path: {sys.path}")
        test_runner = TestRunner()
        if ui_manager:
            ui_manager.send_status_bar("Running initial tests...")
        success = test_runner.run_tests()
        if not success:
            logger.error("Initial Tests failed. They need to be fixed before proceeding. Exiting.")
            if ui_manager:
                ui_manager.send_status_bar("❌ Initial tests failed. Fix tests before proceeding.")
            return False

        project_files = ProjectFiles()
        if ui_manager:
            ui_manager.send_status_bar("Updating project files summary...")
        project_files.update_summaries()
        codebase = project_files.get_codebase_summary()

        # Process image if specified in config
        image_url = config.safe_get('general', 'image')
        if image_url:
            # Run vision LLM to get visual description
            if ui_manager:
                ui_manager.send_status_bar("Processing image...")
            vision_client = LLMClient(llm_type="vision")
            vision_messages = [
                Message(role="system", content="You are a helpful assistant that can analyze images."),
                Message(role="user", content="Please provide a visual description of the image.")
            ]
            visual_description = vision_client.vision_chat_completion(vision_messages, image_url)
            if protoblock is not None:
                protoblock.image_url = image_url
                protoblock.visual_description = visual_description
            else:
                from tac.blocks.generator import ProtoBlockGenerator
                original_create = ProtoBlockGenerator.create_protoblock
                def patched_create(self, protoblock_genesis_prompt, protoblock=None):
                    pb = original_create(self, protoblock_genesis_prompt, protoblock)
                    pb.image_url = image_url
                    pb.visual_description = visual_description
                    return pb
                ProtoBlockGenerator.create_protoblock = patched_create

        if config.general.use_orchestrator:
            if ui_manager:
                ui_manager.send_status_bar("Initializing multi-block orchestrator...")
            multi_block_orchestrator = MultiBlockOrchestrator(ui_manager=ui_manager)
            success = multi_block_orchestrator.execute(task_instructions, codebase, config, None, git_manager)
            
            if success:
                print("\n✅ Multi-block orchestrator completed successfully!")
                logger.info("Multi-block orchestrator completed successfully.")
                if ui_manager:
                    ui_manager.send_status_bar("✅ Multi-block orchestrator completed successfully!")
            else:
                print("\n❌ Multi-block orchestrator execution failed.")
                logger.error("Multi-block orchestrator execution failed.")
                if ui_manager:
                    ui_manager.send_status_bar("❌ Multi-block orchestrator execution failed.")
        else:
            # Use the InteractiveBlockProcessor with overridden commit logic
            if ui_manager:
                ui_manager.send_status_bar("Initializing block processor...")
            block_processor = InteractiveBlockProcessor(task_instructions, codebase, protoblock=protoblock, ui_manager=ui_manager)
            success = block_processor.run_loop()
        
        if success:
            print("\n✅ Task completed successfully!")
            logger.info("Task completed successfully.")
            if ui_manager:
                ui_manager.send_status_bar("✅ Task completed successfully!")
        else:
            print("\n❌ Task execution failed.")
            logger.error("Task execution failed.")
            if ui_manager:
                ui_manager.send_status_bar("❌ Task execution failed.")
        
        return success
            
    except Exception as e:
        logger.error(f"Error during execution: {e}")
        if ui_manager:
            ui_manager.send_status_bar(f"❌ Error during execution: {type(e).__name__}")
        return False

def main():
    parser, args = parse_args()

    if args.ui:
        from tac.web.ui import UIManager
        ui_manager = UIManager()
        ui_manager.launch_ui()
        sys.exit(0)
    
    # Initialize config before any logging
    config.override_with_args(vars(args))
    
    # Set up logging with config values
    # Check environment variable first (highest priority)
    env_log_level = os.environ.get('TAC_LOG_LEVEL')
    
    # Command line args have second highest priority
    # Check both global and subcommand log-level arguments
    cmd_log_level = args.log_level if hasattr(args, "log-level") else None
    
    # Config has lowest priority
    config_log_level = config.logging.get_tac('level', 'INFO')
    
    # Determine final log level
    log_level = env_log_level or cmd_log_level or config_log_level
    log_color = config.logging.get_tac('color', 'green')
    
    # Override the logging config with the final log level
    config.override_with_dict({'logging': {'tac': {'level': log_level}}})
    
    # Create a logger for this function instead of using a global
    logger = setup_logging('tac.cli.main', log_level=log_level, log_color=log_color)
    
    # Update all existing loggers with the new log level
    update_all_loggers(log_level)
    
    logger.debug(f"Starting TAC with log level: {log_level}")
    logger.debug(f"Command: {args.command}")
    logger.debug(f"Arguments: {vars(args)}")
    
    # For the 'view' command, don't set up any logging system
    if args.command == 'view':
        from tac.cli.viewer import TACViewer
        try:
            TACViewer().logs_menu()
        except KeyboardInterrupt:
            print("\nGoodbye!")
            sys.exit(0)
        return
    
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
        if hasattr(args, 'log_level') and args.log_level:
            log_level = args.log_level
            logger = setup_logging('tac.cli.main', log_level=log_level, log_color=log_color)
            config.override_with_dict({'logging': {'tac': {'level': log_level}}})
            update_all_loggers(log_level)
            
        logger.debug(f"Optimizing function: {args.function_name}")
        optimizer = PerformanceTestingAgent(args.function_name, config)
        optimizer.optimize(nmb_runs=5) 
        sys.exit(0)

    if args.command == 'voice':
        from tac.cli.voice import VoiceUI
        try:
            voice_ui = VoiceUI()
            if hasattr(args, 'temperature'):
                voice_ui.temperature = args.temperature
            voice_ui.start()
            logger.info(f"Got voice task instructions: {voice_ui.task_instructions}")
            
            # Create config overrides from args
            config_overrides = {}
            for key in vars(config.general):
                arg_key = key.replace('_', '-')  # Convert underscore to hyphen for CLI args
                if hasattr(args, arg_key) and getattr(args, arg_key) is not None:
                    config_overrides[key] = getattr(args, arg_key)
            
            success = execute_command(
                task_instructions=voice_ui.task_instructions,
                config_overrides=config_overrides,
                ui_manager=None  # VoiceUI doesn't support send_status_bar
            )
            if not success:
                sys.exit(1)
            
        except KeyboardInterrupt:
            print("\nGoodbye!")
            sys.exit(0)

    if args.command == 'make':
        # Extract task instructions from args
        task_instructions = " ".join(args.instructions) if isinstance(args.instructions, list) else args.instructions
        
        # Prepare protoblock from JSON if specified
        protoblock = None
        if args.json:
            from tac.blocks.model import ProtoBlock
            protoblock = ProtoBlock.load(args.json)
            print(f"\n📄 Loaded protoblock from: {args.json}")
        
        # Create config overrides from args
        config_overrides = {}
        for key in vars(config.general):
            arg_key = key.replace('_', '-')  # Convert underscore to hyphen for CLI args
            if hasattr(args, arg_key) and getattr(args, arg_key) is not None:
                config_overrides[key] = getattr(args, arg_key)
        
        # Handle the no-git flag
        if args.no_git:
            config_overrides['git'] = {'enabled': False}
        
        # Set image in config if provided
        if args.image:
            config_overrides['image'] = args.image
        
        success = execute_command(
            task_instructions=task_instructions,
            protoblock=protoblock,
            config_overrides=config_overrides,
            ui_manager=None
        )
        if not success:
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()