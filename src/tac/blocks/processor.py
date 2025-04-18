#!/usr/bin/env python
import os
import sys
import time
import logging
import traceback
from typing import Optional, Dict, Any, List, Tuple, TYPE_CHECKING
import uuid
import json
import asyncio
from datetime import datetime
import git

from tac.blocks.model import ProtoBlock
from tac.blocks.executor import BlockExecutor
from tac.blocks.generator import ProtoBlockGenerator
from tac.utils.ui import NullUIManager
from tac.agents.coding.aider import AiderAgent
from tac.core.log_config import setup_logging
from tac.utils.file_gatherer import gather_python_files
from tac.utils.file_summarizer import FileSummarizer
from tac.core.llm import LLMClient, Message
from tac.utils.git_manager import create_git_manager
from tac.utils.project_files import ProjectFiles
from tac.core.config import config
from tac.agents.trusty.pytest import PytestTestingAgent as TestRunner

# Use TYPE_CHECKING for type hints to avoid circular imports
if TYPE_CHECKING:
    from tac.blocks.executor import BlockExecutor

logger = setup_logging('tac.blocks.processor')

class BlockProcessor:
    """
    Handles the end-to-end workflow given a task instructions and codebase, handling 
 the lifecycle of a coding task from specification to implementation and trust assurances.
    1. Creates a ProtoBlock (task specification) from instructions
    2. Executes the implementation + trust assurances in a looped with retries
    
    Acts as the central coordinator between the generator and executor components.
    """
    def __init__(self, task_instructions=None, codebase=None, protoblock=None, config_override=None, ui_manager=NullUIManager()):
        # Input validation
        if protoblock is None and (task_instructions is None or codebase is None):
            raise ValueError("Either protoblock must be specified, or both task_instructions and codebase must be provided")
        
        self.task_instructions = task_instructions
        self.codebase = codebase
        self.input_protoblock = protoblock
        self.protoblock = None
        self.previous_protoblock = None
        self.ui_manager = ui_manager
        
        # Import BlockExecutor at runtime to avoid circular imports
        from tac.blocks.executor import BlockExecutor
        self.executor = BlockExecutor(config_override=config_override, codebase=codebase, ui_manager=ui_manager)
        
        # Import ProtoBlockGenerator at runtime to avoid circular imports
        from tac.blocks.generator import ProtoBlockGenerator
        self.generator = ProtoBlockGenerator(ui_manager=ui_manager)
        
        # Use the appropriate git manager based on config
        self.git_manager = create_git_manager()

    def create_protoblock(self, idx_attempt, error_analysis):
        if self.input_protoblock:
            # Use the directly provided protoblock
            protoblock = self.input_protoblock
            logger.info("\n✨ Using provided protoblock")
        else:
            # Create protoblock using generator
            
            if error_analysis:
                genesis_prompt = f"{self.task_instructions} \n You have tried to implement this before and it failed, here is the error analysis. In your next attempt, really dig into this and be explicit and do your best to AVOID the error. For instance, if there are any files mentioned that may have been missing in our analysis, you should include them this time into the protoblock. Or if there is a parameter that is undefined and throwing an error, mention it. Here is the full report: {error_analysis}"
                logger.info(f"\n🔄 Generating protoblock from task instructions INCLUDING ERROR ANALYSIS: {genesis_prompt}")
            else:
                genesis_prompt = self.task_instructions
                logger.info(f"\n🔄 Generating protoblock from task instructions: {genesis_prompt}")

            # Generate complete genesis prompt
            protoblock_genesis_prompt = self.generator.get_protoblock_genesis_prompt(self.codebase, genesis_prompt)
            
            # Create protoblock from genesis prompt
            protoblock = self.generator.create_protoblock(protoblock_genesis_prompt)


            # Branch name and commit from the first one!
            if idx_attempt > 0:
                self.override_new_protoblock_with_previous_protoblock(protoblock)
            
            # Save protoblock to file only if enabled in config
            if config.general.save_protoblock:
                json_file = protoblock.save()
                logger.info(f"Saved protoblock to {json_file}")
            else:
                logger.info("Protoblock saving is disabled. Use --save-protoblock to enable.")

        # Set the attempt number based on idx_attempt
        protoblock.attempt_number = idx_attempt + 1
        
        self.protoblock = protoblock

    def override_new_protoblock_with_previous_protoblock(self, protoblock):
        protoblock.block_id  = self.previous_protoblock.block_id
        protoblock.branch_name = self.previous_protoblock.branch_name
        protoblock.commit_message = self.previous_protoblock.commit_message


    def store_previous_protoblock(self):
        self.previous_protoblock = self.protoblock


    def handle_git_branch_setup(self):
        # Handle git branch setup first if git is enabled
        if config.git.enabled:
            current_git_branch = self.git_manager.get_current_branch() or ""
            tac_branch = self.protoblock.branch_name

            # If already on a TAC branch (branch name starts with 'tac/'),
            # then skip branch creation or switching, and use the current branch.
            if current_git_branch.startswith("tac/"):
                logger.info(f"Already on a TAC branch: {current_git_branch}. No branch switching necessary.")
                tac_branch = current_git_branch
            else:
                if not self.git_manager.create_or_switch_to_tac_branch(tac_branch):
                    logger.error(f"Failed to create or switch to tac branch {tac_branch}")
                    return False
                logger.info(f"Switched to tac branch: {tac_branch}")
                
            # Now check git status, but only for tracked files
            status_ok, _ = self.git_manager.check_status(ignore_untracked=True)
            if not status_ok:
                return False
        else:
            logger.info("Git operations disabled")
        return True

    def run_loop(self):
        # Preliminary tests before we start.
        max_retries = config.general.max_retries_block_creation

        # Here we enter the loop for trying to make protoblock and executing it!
        logger.info(f"Starting execution loop, using max_retries={max_retries} from config")

        error_analysis = ""  # Initialize as empty string instead of None

        for idx_attempt in range(max_retries):
            logger.info(f"🔄 Starting block creation and execution attempt {idx_attempt + 1} of {max_retries}", heading=True)
            
            # Since we already created the protoblock in UI.handle_block_click for first attempt,
            # we only need to handle subsequent attempts here
            if idx_attempt > 0:
                # Send status update at beginning of each attempt
                # Make sure the attempt number is correctly reflected
                self.ui_manager.send_status_bar(f"Starting block creation and execution attempt {idx_attempt + 1} of {max_retries}")
                    
                # Halt execution? Pause and let user decide on recovery action on subsequent attempts.
                if config.general.halt_after_fail:
                    user_input = input("Execution paused after failure. Enter 'r' to revert to last commit (clean state), or 'c' to continue with current state: ").strip().lower()
                    if user_input in ['r', 'revert']:
                        if config.git.enabled:
                            logger.info("Reverting changes as per user selection...")
                            self.git_manager.revert_changes()
                        else:
                            logger.info("Git is disabled; cannot revert changes.")
                    elif user_input in ['c', 'continue']:
                        logger.info("Continuing with current state as per user selection...")
                    else:
                        logger.info("Invalid selection, defaulting to continue without reverting.")
                else:
                    if config.git.enabled:
                        logger.info("Reverting changes while staying on feature branch...")
                        self.git_manager.revert_changes()

                # Generate a protoblock for subsequent attempts
                try:
                    # SEND STATUS MESSAGE
                    self.ui_manager.send_status_bar(f"Creating new protoblock for attempt {idx_attempt + 1}...")
                    self.create_protoblock(idx_attempt, error_analysis)
                    self.ui_manager.send_status_bar(f"Protoblock created for attempt {idx_attempt + 1}!")
                        
                    # For web UI, send the protoblock data to display the new protoblock
                    if hasattr(self.ui_manager, 'websocket') and self.ui_manager.websocket and self.protoblock:
                        try:
                            import json
                            import asyncio
                            from functools import partial
                                
                            # Use run_coroutine_threadsafe with a partial function to send the protoblock data
                            asyncio.run_coroutine_threadsafe(
                                self.ui_manager.send_protoblock_data(self.protoblock),
                                self.ui_manager._loop
                            )
                        except Exception as e:
                            logger.error(f"Failed to send protoblock data: {e}")
                except ValueError as exc:
                    error_analysis = str(exc)
                    logger.error(f"Protoblock generation failed on attempt {idx_attempt + 1}: {error_analysis}", heading=True)
                    self.ui_manager.send_status_bar(f"❌ Protoblock generation failed: {error_analysis[:100]}...")
                    self.store_previous_protoblock()
                    continue

            # Handle git branch setup only for first attempt
            if idx_attempt == 0:
                self.ui_manager.send_status_bar("Setting up git branch...")
                if not self.handle_git_branch_setup():
                    self.ui_manager.send_status_bar("❌ Git branch setup failed")
                    return False

            # Execute the protoblock using the builder
            self.ui_manager.send_status_bar(f"Starting coding agent execution for attempt {idx_attempt + 1}...")
            
            execution_success, error_analysis, failure_type = self.executor.execute_block(self.protoblock, idx_attempt)

            if not execution_success:
                logger.error(f"Attempt {idx_attempt + 1} failed. Type: {failure_type}", heading=True)
                self.ui_manager.send_status_bar(f"❌ Execution attempt {idx_attempt + 1} failed: {failure_type}")
                    
                # For web UI, send an explicit message to remove the protoblock display after failure
                if hasattr(self.ui_manager, 'websocket') and self.ui_manager.websocket:
                    try:
                        import json
                        import asyncio
                        asyncio.run_coroutine_threadsafe(
                            self.ui_manager.websocket.send(json.dumps({
                                "type": "remove_protoblock",
                                "message": f"Execution attempt {idx_attempt + 1} failed"
                            })),
                            self.ui_manager._loop
                        )
                    except Exception as e:
                        logger.error(f"Failed to send remove_protoblock message: {e}")
                
                # Only log error analysis if run_error_analysis is enabled in config
                if config.general.trusty_agents.run_error_analysis and error_analysis:
                    logger.error(error_analysis)

                # Store the previous protoblock
                self.store_previous_protoblock()
                
                # Send updated protoblock with results even on failure
                if hasattr(self.ui_manager, 'send_protoblock_data') and hasattr(self.protoblock, 'trusty_agent_results'):
                    logger.info(f"Sending updated protoblock with {len(self.protoblock.trusty_agent_results)} trusty agent results after failure")
                    # Import asyncio here to make sure it's available
                    import asyncio
                    asyncio.run_coroutine_threadsafe(
                        self.ui_manager.send_protoblock_data(self.protoblock),
                        self.ui_manager._loop
                    )
                
                # If run_error_analysis is disabled, set error_analysis to empty string
                if not config.general.trusty_agents.run_error_analysis:
                    error_analysis = ""
            else:
                self.ui_manager.send_status_bar(f"✅ Execution successful for attempt {idx_attempt + 1}!")
                
                # Debug log to show if we have trusty agent results
                if hasattr(self.protoblock, 'trusty_agent_results') and self.protoblock.trusty_agent_results:
                    logger.info(f"Protoblock has {len(self.protoblock.trusty_agent_results)} trusty agent results")
                    for agent_name, result in self.protoblock.trusty_agent_results.items():
                        logger.info(f"Agent {agent_name} result: status={result.get('status', 'unknown')}")
                else:
                    logger.warning("No trusty agent results found in protoblock!")
                
                # Send updated protoblock with results
                if hasattr(self.ui_manager, 'send_protoblock_data'):
                    logger.info("Sending updated protoblock with results to UI...")
                    if hasattr(self.protoblock, 'trusty_agent_results'):
                        result_keys = list(self.protoblock.trusty_agent_results.keys())
                        logger.info(f"Trusty agent result keys: {result_keys}")
                    
                    # Import asyncio here to make sure it's available
                    import asyncio
                    
                    asyncio.run_coroutine_threadsafe(
                        self.ui_manager.send_protoblock_data(self.protoblock),
                        self.ui_manager._loop
                    )
                
                # Handle git operations if enabled and execution was successful
                if config.git.enabled:
                    if config.safe_get('general', 'halt_after_verify'):
                        logger.info("Halt after successful verification is enabled.")
                        while True:
                            choice = input("Verification successful! Enter 'c' to commit changes, or 'a' to abort: ").strip().lower()
                            if choice == 'c':
                                commit_success = self.git_manager.handle_post_execution(config.raw_config, self.protoblock.commit_message)
                                if commit_success:
                                    logger.info("Changes committed successfully.")
                                    break
                                else:
                                    logger.error("Failed to commit changes")
                                    return False
                            elif choice == 'a':
                                logger.info("User chose to abort. Reverting changes...")
                                self.git_manager.revert_changes()
                                logger.info("Exiting without committing changes.")
                                break
                            else:
                                logger.info("Invalid selection. Please enter 'c' to commit or 'a' to abort.")
                    else:
                        commit_success = self.git_manager.handle_post_execution(config.raw_config, self.protoblock.commit_message)
                        if not commit_success:
                            logger.error("Failed to commit changes")
                            return False
                return True
            
        # If we've reached here, all attempts failed
        if config.git.enabled and self.protoblock:
            current_branch = self.git_manager.get_current_branch()
            base_branch = self.git_manager.base_branch if self.git_manager.base_branch else "main"
            
            # Print cleanup instructions
            logger.error("❌ All execution attempts failed", heading=True)
            logger.error("📋 Git Cleanup Commands:")
            logger.error(f"  To switch back to your main branch and clean up:")
            logger.error(f"    git switch {base_branch} && git restore . && git clean -fd && git branch -D {current_branch}")
            
        return False 