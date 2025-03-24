#!/usr/bin/env python3
import os
import sys
import time
import tempfile
import subprocess
import logging
from typing import Dict, Tuple, Optional, Union, Any
import platform
import uuid

from playwright.sync_api import sync_playwright

from tac.core.llm import LLMClient, Message
from tac.blocks import ProtoBlock
from tac.core.config import config
from tac.core.log_config import setup_logging
from tac.trusty_agents.base import TrustyAgent, ComparativeTrustyAgent, trusty_agent
from tac.utils.web_utils import (
    verify_page_load, 
    take_page_screenshot,
    generate_unique_screenshot_path,
    analyze_screenshot,
    determine_vision_success,
    verify_page_load_with_browser,
    PLAYWRIGHT_AVAILABLE,
    ensure_playwright_installed
)
from tac.utils.image_stitcher import stitch_images

logger = setup_logging('tac.trusty_agents.threejs_vision_before_after')

@trusty_agent(
    name="threejs_vision_before_after",
    description="For comparisons between the current and the planned implementation. Compares visual changes in Three.js applications before and after code changes. Shows before/after screenshots side by side.",
    protoblock_prompt="Describe the expected visual changes between the before and after states. Focus on what should be different, like new elements, changed colors, or different layouts.",
    prompt_target="coding_agent"
)
class ThreeJSVisionBeforeAfterAgent(ComparativeTrustyAgent):
    """
    A trusty agent that captures screenshots before and after code changes,
    stitches them together side by side, and analyzes the differences.
    """

    def __init__(self):
        logger.info("Initializing ThreeJSVisionBeforeAfterAgent")
        self.llm_client = LLMClient(llm_type="vision")
        self.before_screenshot_path = None
        self.after_screenshot_path = None
        self.comparison_path = None
        self.analysis_result = None
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.protoblock = None

    def set_protoblock(self, protoblock: ProtoBlock) -> None:
        """Set the protoblock for use in state capture."""
        self.protoblock = protoblock

    def _capture_state(self) -> str:
        """
        Capture a screenshot of the current state.
        
        Returns:
            str: Path to the screenshot file
        """
        try:
            # Get the HTML file path
            app_file_path = self._get_app_file_path(self.protoblock)
            if not app_file_path:
                raise ValueError("Could not determine which HTML file to run")
            
            if not os.path.exists(app_file_path):
                raise ValueError(f"HTML file not found: {app_file_path}")
            
            # Launch browser if not already running
            if not self.playwright:
                self.playwright = sync_playwright().start()
                self.browser = self.playwright.chromium.launch(headless=True)
                self.context = self.browser.new_context()
                self.page = self.context.new_page()
            
            # Navigate to URL
            file_url = f"file://{os.path.abspath(app_file_path)}"
            logger.info(f"Navigating to: {file_url}")
            response = self.page.goto(file_url, wait_until="networkidle", timeout=30000)
            if not response or not response.ok:
                raise ValueError(f"Failed to load page: {response.status if response else 'No response'}")
            
            # Verify page load
            success, errors, _ = verify_page_load(self.page, timeout=30000)
            if not success:
                raise ValueError("\n".join(errors))
            
            # Take screenshot
            screenshot_path = take_page_screenshot(self.page)
            logger.info(f"Screenshot saved: {screenshot_path}")
            
            return screenshot_path
            
        except Exception as e:
            logger.exception(f"Error capturing state: {str(e)}")
            raise

    def capture_before_state(self) -> None:
        """Capture the initial state before changes."""
        if not self.protoblock:
            raise ValueError("Protoblock not set. Call set_protoblock first.")
        self.before_screenshot_path = self._capture_state()

    def _check_impl(self, protoblock: ProtoBlock, codebase: str, code_diff: str) -> Tuple[bool, str, str]:
        """
        Compare the before and after states.
        
        Args:
            protoblock: The ProtoBlock containing task specifications
            codebase: Dictionary mapping file paths to their contents
            code_diff: The git diff showing implemented changes
            
        Returns:
            Tuple containing:
            - bool: Success status
            - str: Error analysis
            - str: Failure type
        """
        try:
            # Store the protoblock for use in _capture_state
            self.protoblock = protoblock
            
            # Verify we have the before state
            if not self.before_screenshot_path:
                return False, "No initial state captured", "Missing before state"
            
            # Capture after state
            self.after_screenshot_path = self._capture_state()
            
            # Create comparison image
            self.comparison_path = os.path.join(
                os.path.dirname(self.before_screenshot_path),
                f"comparison_{uuid.uuid4()}.png"
            )
            
            # Stitch images together
            comparison_img = stitch_images(
                self.before_screenshot_path,
                self.after_screenshot_path,
                border=10,
                border_color="black"
            )
            comparison_img.save(self.comparison_path)
            logger.info(f"Comparison image saved: {self.comparison_path}")
            
            # Get expected changes from protoblock
            expected_changes = protoblock.trusty_agent_prompts.get("threejs_vision_before_after", "")
            if not expected_changes:
                expected_changes = "Analyze the visual differences between the before and after states."
            
            # Analyze the comparison
            prompt = f"The left side is the before state and the right side is the after state. Analyze this side-by-side comparison with the expected changes: {expected_changes}"
            logger.info(f"Analyzing comparison with prompt: {prompt}")
            self.analysis_result = analyze_screenshot(self.comparison_path, prompt, self.llm_client)
            
            # Determine success
            success = determine_vision_success(self.analysis_result, config.general.trusty_agents.minimum_vision_score.upper())
            
            if success:
                return True, "", ""
            else:
                return False, self.analysis_result, "Visual comparison failed"
            
        except Exception as e:
            logger.exception(f"Error in visual comparison: {str(e)}")
            return False, str(e), "Visual comparison error"
            
        finally:
            # Clean up resources
            if self.context:
                try:
                    self.context.close()
                except Exception as e:
                    logger.error(f"Error closing context: {e}")
                    
            if self.browser:
                try:
                    self.browser.close()
                except Exception as e:
                    logger.error(f"Error closing browser: {e}")
                    
            if self.playwright:
                try:
                    self.playwright.stop()
                except Exception as e:
                    logger.error(f"Error stopping playwright: {e}")

    def _get_app_file_path(self, protoblock: ProtoBlock) -> Optional[str]:
        """
        Determine which HTML file to run based on the protoblock.
        
        Args:
            protoblock: The ProtoBlock containing task specifications
            
        Returns:
            str: Path to the HTML file to run, or None if not found
        """
        # First check for HTML files with "index" in the name
        for file_path in protoblock.write_files:
            if file_path.endswith('.html') and 'index' in file_path.lower():
                return file_path
        
        # Then check for any HTML file
        for file_path in protoblock.write_files:
            if file_path.endswith('.html'):
                return file_path
                
        # If no HTML file found in write_files, check context_files
        for file_path in protoblock.context_files:
            if file_path.endswith('.html') and 'index' in file_path.lower():
                return file_path
                
        for file_path in protoblock.context_files:
            if file_path.endswith('.html'):
                return file_path
        
        return None 