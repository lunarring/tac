#!/usr/bin/env python3
import os
import sys
import time
import tempfile
import subprocess
import logging
from typing import Dict, Tuple, Optional, Any
import platform
import uuid

from playwright.sync_api import sync_playwright

from tac.core.llm import LLMClient, Message
from tac.blocks import ProtoBlock
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
from PIL import Image

logger = setup_logging('tac.trusty_agents.threejs_vision_reference')

@trusty_agent(
    name="threejs_vision_reference",
    description="Compares the current visual state of a Three.js application against a provided reference image. Captures before and after screenshots, stitches them with the reference image, and uses a vision LLM for analysis.",
    protoblock_prompt="Describe the expected differences between the current implementation and the provided reference design.",
    prompt_target="coding_agent"
)
class ThreeJSVisionReferenceAgent(ComparativeTrustyAgent):
    """
    A trusty agent that captures screenshots before and after code changes,
    stitches them together with a reference image (provided via CLI) side by side,
    and analyzes the visual differences between the current state and the reference.
    The order of images is: before, after, reference.
    """

    def __init__(self):
        logger.info("Initializing ThreeJSVisionReferenceAgent")
        self.llm_client = LLMClient(llm_type="vision")
        self.before_screenshot_path = None
        self.after_screenshot_path = None
        self.comparison_path = None
        self.analysis_result = None
        self.reference_image_path = None
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.protoblock = None

    def set_protoblock(self, protoblock: ProtoBlock) -> None:
        """Set the protoblock for use in state capture."""
        self.protoblock = protoblock

    def set_reference_image(self, reference_image_path: str) -> None:
        """Set the reference image provided via the CLI."""
        if not os.path.exists(reference_image_path):
            raise ValueError(f"Reference image not found: {reference_image_path}")
        self.reference_image_path = reference_image_path

    def _ensure_browser(self):
        """Ensure browser resources are available and properly initialized."""
        try:
            if not self.playwright:
                self.playwright = sync_playwright().start()
                self.browser = self.playwright.chromium.launch(headless=True)
                self.context = self.browser.new_context()
                self.page = self.context.new_page()
            elif not self.page:
                # If page is closed but other resources exist, create a new page
                self.page = self.context.new_page()
        except Exception as e:
            logger.error(f"Error ensuring browser: {e}")
            self._cleanup_browser()
            raise

    def _cleanup_browser(self):
        """Clean up browser resources."""
        try:
            if self.context:
                self.context.close()
                self.context = None
            if self.browser:
                self.browser.close()
                self.browser = None
            if self.playwright:
                self.playwright.stop()
                self.playwright = None
            self.page = None
        except Exception as e:
            logger.error(f"Error cleaning up browser: {e}")

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
            
            # Ensure browser is ready
            self._ensure_browser()
            
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
            self._cleanup_browser()  # Clean up on error
            raise

    def capture_before_state(self) -> None:
        """Capture the initial state before changes."""
        if not self.protoblock:
            raise ValueError("Protoblock not set. Call set_protoblock first.")
        self.before_screenshot_path = self._capture_state()

    def _check_impl(self, protoblock: ProtoBlock, codebase: str, code_diff: str) -> Tuple[bool, str, str]:
        """
        Compare the before and after states with the provided reference image.
        
        Args:
            protoblock: The ProtoBlock containing task specifications
            codebase: Dictionary mapping file paths to their contents
            code_diff: The git diff showing implemented changes
            
        Returns:
            Tuple containing:
            - bool: Success status
            - str: Analysis from vision LLM
            - str: Failure type or empty string if successful
        """
        try:
            # Store the protoblock for use in _capture_state
            self.protoblock = protoblock

            if not self.reference_image_path:
                return False, "Reference image not provided", "Missing reference image"
            
            # Verify we have the before state
            if not self.before_screenshot_path:
                return False, "No initial state captured", "Missing before state"
            
            # Capture after state
            self.after_screenshot_path = self._capture_state()
            
            # Create comparison image by stitching before, after, and reference images side by side.
            self.comparison_path = os.path.join(
                os.path.dirname(self.before_screenshot_path),
                f"comparison_{uuid.uuid4()}.png"
            )
            
            comparison_img = stitch_images(
                self.before_screenshot_path,
                self.after_screenshot_path,
                self.reference_image_path,
                border=10,
                border_color="black"
            )
            comparison_img.save(self.comparison_path)
            logger.info(f"Comparison image saved: {self.comparison_path}")
            
            # Get expected changes from protoblock; if not provided use a default prompt.
            expected_changes = protoblock.trusty_agent_prompts.get("threejs_vision_reference", "")
            if not expected_changes:
                expected_changes = "Compare the current implementation against the provided reference image."
            
            # Create a detailed prompt for analysis
            prompt = f"""Analyze this side-by-side comparison of a Three.js application:
- Left pane shows the before state.
- Middle pane shows the after state (current implementation).
- Right pane shows the provided reference image.
Expected changes: {expected_changes}

Please provide a simple verification:
- Answer YES if the current state (after) visually matches the reference.
- Answer NO if it does not match well.

Also, include a brief explanation of your reasoning."""
            
            messages = [
                Message(role="system", content="You are a visual analysis assistant."),
                Message(role="user", content=prompt)
            ]
            
            logger.info(f"Analyzing comparison with prompt: {prompt}")
            self.analysis_result = self.llm_client.vision_chat_completion(messages, self.comparison_path)
            logger.info(f"Visual comparison analysis:\n{self.analysis_result}")
            
            # Parse the analysis_result to determine success: if "YES" is present (case-insensitive) then success.
            if "yes" in self.analysis_result.lower():
                return True, self.analysis_result, ""
            else:
                return False, self.analysis_result, "Visual comparison failed"
            
        except Exception as e:
            logger.exception(f"Error in visual comparison: {str(e)}")
            return False, str(e), "Visual comparison error"
            
        finally:
            # Clean up browser resources
            self._cleanup_browser()

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