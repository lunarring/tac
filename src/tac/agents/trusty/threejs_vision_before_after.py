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
import re

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
        self.stars = None
        self.grade = None
        self.grade_info = None

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
1. STAR RATING: [0.0-5.0] - Overall rating for the implementation
2. ANALYSIS: Detailed explanation of what changed and why the rating was given
3. IMPROVEMENTS: Specific suggestions for improvement if rating is below 4.0

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
                You will rate the visualization on a scale from 0 to 5 stars where:
                5.0 stars: Perfect match with all expected elements present and correctly rendered
                4.0 stars: Good match with minor visual discrepancies
                3.0 stars: Acceptable but with noticeable issues
                2.0 stars: Poor with significant rendering problems but basic elements visible
                1.0 stars: Very poor with major elements incorrectly rendered
                0.0 stars: Failed - major elements missing or severe rendering problems
                
                Provide your analysis in this format:
                
                STAR RATING: [0.0-5.0]
                
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
            
            # Determine success with minimum star rating 4.0
            success = determine_vision_success(self.analysis_result, 4.0)
            
            # Store star rating for UI display if available
            try:
                if "STAR RATING:" in self.analysis_result:
                    rating_line = self.analysis_result.split("STAR RATING:")[1].split("\n")[0].strip()
                    # Clean up any markdown formatting (e.g., ** for bold)
                    rating_line = rating_line.replace("*", "")
                    
                    # More robust regex to extract numeric values
                    numbers = re.findall(r'\d+\.?\d*', rating_line)
                    if numbers:
                        stars = float(numbers[0])
                        # Ensure the rating is within bounds
                        stars = max(0.0, min(5.0, stars))
                        
                        # Store the star rating for UI display - ensure both properties are set
                        self.stars = stars
                        self.grade = f"{stars:.1f}"  # Format to 1 decimal place as string
                        
                        # Add a field indicating the star rating scale for UI display
                        self.grade_info = {
                            5.0: "Excellent - Perfect match with requirements",
                            4.5: "Very good - Almost perfect with minor issues",
                            4.0: "Good - Minor visual discrepancies", 
                            3.5: "Above average - Some issues but mostly good",
                            3.0: "Acceptable - Noticeable issues",
                            2.5: "Below average - Multiple issues",
                            2.0: "Poor - Significant rendering problems",
                            1.5: "Very poor - Major issues",
                            1.0: "Very poor - Major elements incorrect",
                            0.5: "Almost failed - Barely recognizable",
                            0.0: "Failed - Major elements missing"
                        }.get(round(stars * 2) / 2, f"{stars:.1f} stars")
                        
                        # Debug log with more details
                        logger.info(f"Extracted star rating from line '{rating_line}': {stars}, Grade: {self.grade}, Info: {self.grade_info}")
                elif "GRADE:" in self.analysis_result:
                    # Legacy grade format - convert to stars
                    grade_line = self.analysis_result.split("GRADE:")[1].split("\n")[0].strip()
                    grade = grade_line[0].upper() if grade_line else ""
                    
                    # Convert letter grade to stars
                    grade_to_stars = {"A": 5.0, "B": 4.0, "C": 3.0, "D": 2.0, "F": 0.0}
                    if grade in grade_to_stars:
                        self.stars = grade_to_stars[grade]
                        self.grade = f"{self.stars:.1f}"
                        self.grade_info = f"Converted from grade {grade}"
                        logger.info(f"Converted grade {grade} to stars: {self.stars}")
            except Exception as e:
                logger.error(f"Error processing star rating for UI: {e}")
                
            # Ensure we have grade and stars properties set for UI display
            if self.grade is None and success:
                self.grade = "4.0"  # Default to 4.0 stars for success
                self.stars = 4.0
                self.grade_info = "Default success rating"
            elif self.grade is None and not success:
                self.grade = "2.0"  # Default to 2.0 stars for failure
                self.stars = 2.0
                self.grade_info = "Default failure rating"
            
            # Check if we've properly set the star rating and make sure it's available for the UI
            logger.info(f"### DEBUG - Before final return: stars={self.stars}, grade={self.grade}, grade_info={self.grade_info}")
            
            # Final check before returning to ensure star rating properties are set
            if self.stars is None or self.grade is None:
                # Fallback - extract from the analysis_result again
                try:
                    if "STAR RATING:" in self.analysis_result:
                        rating_line = self.analysis_result.split("STAR RATING:")[1].split("\n")[0].strip()
                        # Clean up any markdown formatting
                        rating_line = rating_line.replace("*", "")
                        
                        # Extract numeric value
                        import re
                        numbers = re.findall(r'\d+\.?\d*', rating_line)
                        if numbers:
                            stars = float(numbers[0])
                            # Ensure the rating is within bounds
                            stars = max(0.0, min(5.0, stars))
                            
                            # Set properties for UI display
                            self.stars = stars
                            self.grade = f"{stars:.1f}"
                            
                            # Use detailed grade_info mapping
                            self.grade_info = {
                                5.0: "Excellent - Perfect match with requirements",
                                4.5: "Very good - Almost perfect with minor issues",
                                4.0: "Good - Minor visual discrepancies", 
                                3.5: "Above average - Some issues but mostly good",
                                3.0: "Acceptable - Noticeable issues",
                                2.5: "Below average - Multiple issues",
                                2.0: "Poor - Significant rendering problems",
                                1.5: "Very poor - Major issues",
                                1.0: "Very poor - Major elements incorrect",
                                0.5: "Almost failed - Barely recognizable",
                                0.0: "Failed - Major elements missing"
                            }.get(round(stars * 2) / 2, f"{stars:.1f} stars")
                            
                            logger.info(f"Final extraction - Star rating: {stars}, Grade: {self.grade}")
                except Exception as e:
                    logger.error(f"Final extraction error: {e}")
                    # Last resort default values
                    if success and not self.stars:
                        self.stars = 4.0
                        self.grade = "4.0"
                        self.grade_info = "Default success rating"
                    elif not success and not self.stars:
                        self.stars = 2.0
                        self.grade = "2.0"
                        self.grade_info = "Default failure rating"
            
            # Make sure grade is string format with one decimal place
            if self.stars is not None and (self.grade is None or not isinstance(self.grade, str)):
                self.grade = f"{self.stars:.1f}"
            
            logger.info(f"### FINAL VALUES - stars={self.stars}, grade={self.grade}, grade_info={self.grade_info}")
            
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