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
from tac.agents.trusty.base import TrustyAgent, ComparativeTrustyAgent, trusty_agent
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

logger = setup_logging('tac.trusty_agents.threejs_vision_before_after')

@trusty_agent(
    name="threejs_vision_before_after",
    description="Use this trusty agent to verify the visual output of web applications if we have a previous version and can compare to the current implementation. This is useful to see if the expected changes are implemented correctly. Always use it in case we have a previous version and can compare to the current implementation. Shows before/after screenshots side by side.",
    protoblock_prompt="Describe the expected visual changes between left side (previous) and right side (current) that you would expect given the task instructions. Directly describe the scene and what to expect.",
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
            
            # Verify that screenshots exist and have content
            for img_path, img_name in [(self.before_screenshot_path, "Before"), (self.after_screenshot_path, "After")]:
                if not os.path.exists(img_path):
                    return False, f"{img_name} screenshot file not found: {img_path}", f"Missing {img_name.lower()} screenshot"
                    
                file_size = os.path.getsize(img_path)
                if file_size == 0:
                    return False, f"{img_name} screenshot file is empty: {img_path}", f"Empty {img_name.lower()} screenshot"
                
                logger.info(f"{img_name} screenshot verified: {img_path} ({file_size} bytes)")
            
            # Create a temporary dummy image to act as the middle pane.
            # This dummy image is 1 pixel wide and filled with the border color.
            before_img = Image.open(self.before_screenshot_path)
            after_img = Image.open(self.after_screenshot_path)
            max_height = max(before_img.height, after_img.height)
            dummy_img = Image.new("RGB", (1, max_height), color="black")
            dummy_temp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            dummy_img.save(dummy_temp.name, format="PNG")
            dummy_temp.close()
            dummy_image_path = dummy_temp.name
            
            # Create comparison image path
            self.comparison_path = os.path.join(
                os.path.dirname(self.before_screenshot_path),
                f"comparison_{uuid.uuid4()}.png"
            )
            
            # Stitch images together: before, dummy, and after.
            comparison_img = stitch_images(
                self.before_screenshot_path,
                dummy_image_path,
                self.after_screenshot_path,
                border=10,
                border_color="black"
            )
            comparison_img.save(self.comparison_path)
            logger.info(f"Comparison image saved: {self.comparison_path}")
            
            # Verify the comparison image was created properly
            if not os.path.exists(self.comparison_path):
                return False, "Failed to create comparison image", "Image stitching failed"
                
            comparison_file_size = os.path.getsize(self.comparison_path)
            if comparison_file_size == 0:
                return False, "Comparison image file is empty", "Empty comparison image"
                
            logger.info(f"Comparison image verified: {self.comparison_path} ({comparison_file_size} bytes)")
            
            # Clean up the temporary dummy image file.
            os.unlink(dummy_image_path)
            
            # Get expected changes from protoblock
            expected_changes = protoblock.trusty_agent_prompts.get("threejs_vision_before_after", "")
            if not expected_changes:
                expected_changes = "Analyze the visual differences between the before and after states."
            
            # Create a detailed prompt for analysis
            prompt = f"""Analyze this side-by-side comparison of a Three.js application:
- Left side shows the before state
- Right side shows the after state
- Expected changes: {expected_changes}

Please provide:
1. GRADE: [A-F] - Overall grade for the implementation
2. ANALYSIS: Detailed explanation of what changed and why the grade was given
3. IMPROVEMENTS: Specific suggestions for improvement if grade is below A

Focus on:
- Visual accuracy of the changes
- Implementation completeness
- Quality of the visual elements
- Any unexpected or missing changes"""
            
            logger.info(f"Analyzing comparison with prompt: {prompt}")
            
            # Sleep to ensure the image is fully written to disk
            time.sleep(2)
            
            # Direct call to LLM client for vision analysis to ensure image is passed correctly
            messages = [
                Message(role="system", content="""You are a helpful assistant that can analyze 3D visualizations created with Three.js.
                You will grade the visualization on a scale from A to F where:
                A: Perfect match with all expected elements present and correctly rendered
                B: Good match with minor visual discrepancies
                C: Acceptable but with noticeable issues
                D: Minimum passing grade - basic elements present but with significant issues
                F: Failed - major elements missing or severe rendering problems
                
                Provide your analysis in this format:
                
                GRADE: [A-F]
                
                ANALYSIS:
                (Detailed analysis of what matches or doesn't match expectations)
                
                ISSUES:
                (List any visual issues or missing elements)
                
                RECOMMENDATIONS:
                (Suggestions for improvement if needed)"""),
                Message(role="user", content=prompt)
            ]
            
            # Use vision_chat_completion with the comparison image path
            logger.info(f"Sending comparison image to vision model: {self.comparison_path}")
            self.analysis_result = self.llm_client.vision_chat_completion(messages, self.comparison_path)
            
            # Log the detailed analysis
            logger.info(f"Visual comparison analysis:\n{self.analysis_result}")
            
            # Determine success with minimum grade B
            success = determine_vision_success(self.analysis_result, "B")
            
            if success:
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