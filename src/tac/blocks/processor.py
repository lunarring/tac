#!/usr/bin/env python
import os
import sys
import time
import logging
import traceback
from typing import Optional, Dict, Any, List, Tuple, TYPE_CHECKING
import uuid
import json
from datetime import datetime
import git

from tac.blocks.model import ProtoBlock
# Remove direct import to break circular dependency
# from tac.blocks.generator import ProtoBlockGenerator
# Remove direct import to break circular dependency
# from tac.blocks.executor import BlockExecutor
from tac.coding_agents.aider import AiderAgent
from tac.core.log_config import setup_logging
from tac.utils.file_gatherer import gather_python_files
from tac.utils.file_summarizer import FileSummarizer
from tac.core.llm import LLMClient, Message
from tac.utils.git_manager import create_git_manager
from tac.utils.project_files import ProjectFiles
from tac.core.config import config
from tac.trusty_agents.pytest import PytestTestingAgent as TestRunner

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
    def __init__(self, task_instructions=None, codebase=None, protoblock=None, config_override=None):
        # Input validation
        if protoblock is None and (task_instructions is None or codebase is None):
            raise ValueError("Either protoblock must be specified, or both task_instructions and codebase must be provided")
        
        self.task_instructions = task_instructions
        self.codebase = codebase
        self.input_protoblock = protoblock
        self.protoblock = None
        self.previous_protoblock = None
        
        # Import BlockExecutor at runtime to avoid circular imports
        from tac.blocks.executor import BlockExecutor
        self.executor = BlockExecutor(config_override=config_override, codebase=codebase)
        
        # Import ProtoBlockGenerator at runtime to avoid circular imports
        from tac.blocks.generator import ProtoBlockGenerator
        self.generator = ProtoBlockGenerator()
        
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
            logger.debug(f"Protoblock genesis prompt: {protoblock_genesis_prompt}")
            
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

            # Halt execution? Also revert the changes on the feature branch if git is enabled
            if idx_attempt > 0:
                # Only show pause prompt if halt_after_fail is true in config
                if config.general.halt_after_fail:
                    input("Execution paused: press Enter to continue with the next attempt, or Ctrl+C to abort...")

                # Revert changes on the feature branch if git is enabled
                if config.git.enabled :
                    logger.info("Reverting changes while staying on feature branch...")
                    self.git_manager.revert_changes()


            # Generate a protoblock
            self.create_protoblock(idx_attempt, error_analysis)

            # Handle git branch setup first if git is enabled
            if idx_attempt == 0:
                if not self.handle_git_branch_setup():
                    return False

            # Execute the protoblock using the builder
            execution_success, error_analysis, failure_type  = self.executor.execute_block(self.protoblock, idx_attempt)

            if not execution_success:
                logger.error(f"Attempt {idx_attempt + 1} failed. Type: {failure_type}", heading=True)
                
                # Only log error analysis if run_error_analysis is enabled in config
                if config.general.trusty_agents.run_error_analysis and error_analysis:
                    logger.error(error_analysis)

                # Store the previous protoblock
                self.store_previous_protoblock()
                
                # If run_error_analysis is disabled, set error_analysis to empty string
                if not config.general.trusty_agents.run_error_analysis:
                    error_analysis = ""
            else:
                # Handle git operations if enabled and execution was successful
                if config.git.enabled:
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