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
from typing import Dict
logger = setup_logging('tac.core.block_runner')

class BlockRunner:
    def __init__(self, task_instructions=None, codebase=None, json_file=None, config_override=None):
        # Input validation
        if json_file is None and (task_instructions is None or codebase is None):
            raise ValueError("Either json_file must be specified, or both task_instructions and codebase must be provided")
        
        self.task_instructions = task_instructions
        self.codebase = codebase
        self.json_file = json_file
        self.protoblock = None
        self.previous_protoblock = None
        self.executor = ProtoBlockExecutor(config_override=config_override, codebase=codebase)
        self.git_manager = GitManager()


    def generate_protoblock(self, idx_attempt, error_analysis):
        if self.json_file: 
            # in case the protoblock is fixed, we load it from the json file every time
            protoblock = load_protoblock_from_json(self.json_file)
            logger.info(f"\n✨ Loaded protoblock: {self.json_file}")
        else:
            # Create protoblock using factory
            factory = ProtoBlockFactory()
            if error_analysis:
                genesis_prompt = f"{self.task_instructions} \n Last time we tried this, it failed, here is the error analysis, try to do it better this time! For instance, if there are any files mentioned that may have been missing in our analysis, you should include them this time into the protoblock. Here is the full report: {error_analysis}"
                logger.info(f"\n🔄 Generating protoblock from task instructions INCLUDING ERROR ANALYSIS: {genesis_prompt}")
            else:
                genesis_prompt = self.task_instructions
                logger.info(f"\n🔄 Generating protoblock from task instructions: {genesis_prompt}")

            # Generate complete genesis prompt
            protoblock_genesis_prompt = factory.get_protoblock_genesis_prompt(self.codebase, genesis_prompt)
            
            # Create protoblock from genesis prompt
            protoblock = factory.create_protoblock(protoblock_genesis_prompt)

            # Branch name and commit from the first one!
            if idx_attempt > 0:
                self.override_new_protoblock_with_previous_protoblock(protoblock)
            
            # Save protoblock to file
            json_file = factory.save_protoblock(protoblock)

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
            
            if current_git_branch.startswith("tac/"):
                logger.info(f"Already on a TAC branch: {current_git_branch}. No branch switching necessary.")
                tac_branch = current_git_branch
            else:
                if not self.git_manager.create_or_switch_to_tac_branch(tac_branch):
                    logger.error(f"Failed to create or switch to TAC branch {tac_branch}")
                    return False
                logger.info(f"Switched to TAC branch: {tac_branch}")
                
            # Now check git status, but only for tracked files
            status_ok, _ = self.git_manager.check_status(ignore_untracked=True)
            if not status_ok:
                return False
        else:
            logger.info("Git operations disabled")

    def run_loop(self):

        # Preliminary tests before we start.
        max_retries = config.general.max_retries

        # Here we enter the loop for trying to make protoblock and executing it!
        logger.info(f"Starting execution loop, using max_retries={max_retries} from config")

        error_analysis = None

        for idx_attempt in range(max_retries):
            logger.info("="*60)
            logger.info(f"🔄 Starting block creation and execution attempt {idx_attempt + 1} of {max_retries}")
            logger.info("="*60)

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
            self.generate_protoblock(idx_attempt, error_analysis)

            # Handle git branch setup first if git is enabled
            if idx_attempt == 0:
                self.handle_git_branch_setup()


            # Execute the protoblock
            execution_success, failure_type, error_analysis = self.executor.execute_block(self.protoblock, idx_attempt)

            if not execution_success:
                logger.error(f"Attempt {idx_attempt + 1} failed. Type: {failure_type}")
                logger.error("="*50)
                logger.error(error_analysis)
                logger.error("="*50)

                # Store the previous protoblock
                self.store_previous_protoblock()
            else:
                break
            
        # Handle git operations if enabled and execution was successful
        if execution_success and config.git.enabled:
            commit_success = self.git_manager.handle_post_execution(config.raw_config, self.protoblock.commit_message)
            if not commit_success:
                logger.error("Failed to commit changes")
                return False
            return True
        else:
            return False




        