#!/usr/bin/env python3
import os
import sys
import time
import tempfile
import subprocess
import logging
from typing import Dict, Tuple, Optional, Any, Union
import platform
import uuid

from playwright.sync_api import sync_playwright

from tac.core.llm import LLMClient, Message
from tac.blocks import ProtoBlock
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
from tac.core.config import config
from tac.agents.trusty.results import TrustyAgentResult
from PIL import Image

logger = setup_logging('tac.trusty_agents.web_reference')

@trusty_agent(
    name="web_reference",
    description="Use this trusty agent in case we have a reference image input and are developing something with javascript, html, threejs. Compares the current visual state of a web application against a provided reference image. Captures before and after screenshots, stitches them with the reference image, and uses a vision LLM for analysis.",
    protoblock_prompt="On the left side you see the previous implementation, in the middle is the updated implementation and on the right side you see the provided reference image. Describe the expected changes between the previous implementation and the updated implementation given the reference image.",
    prompt_target="coding_agent",
    llm="gpt-4o"
)
class WebReferenceAgent(ComparativeTrustyAgent):
    """
    A trusty agent that captures screenshots before and after code changes,
    stitches them together with a reference image (provided via CLI or protoblock) side by side,
    and analyzes the visual differences between the current state and the reference.
    The order of images is: before, after, reference.
    """

    def __init__(self):
        logger.info("Initializing WebReferenceAgent")
        self.llm_client = LLMClient(component="vision")
        self.before_screenshot_path = None
        self.after_screenshot_path = None
        self.comparison_path = None
        self.analysis_result = None
        self.reference_image_path = None
        self.reference_image = None
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.protoblock = None

    def set_protoblock(self, protoblock: ProtoBlock) -> None:
        """Set the protoblock for use in state capture."""
        self.protoblock = protoblock

    def set_reference_image(self, reference_image_path: str) -> None:
        """Set the reference image provided via the CLI or protoblock."""
        if not os.path.exists(reference_image_path):
            logger.error(f"Reference image not found: {reference_image_path}")
            self.reference_image = None
            self.reference_image_path = None
            return
        try:
            with Image.open(reference_image_path) as img:
                img.verify()
            # Reopen image after verify() as the image gets closed
            with Image.open(reference_image_path) as img:
                self.reference_image = img.copy()
            self.reference_image_path = reference_image_path
            logger.info("Reference image loaded and verified successfully.")
            # TODO: Placeholder for any future image processing steps
        except Exception as e:
            logger.error(f"Failed to load reference image: {str(e)}")
            self.reference_image = None
            self.reference_image_path = None

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

    def _determine_success(self, analysis_result: str) -> bool:
        """
        Determine if the visual comparison analysis indicates success based on a grade.
        Only an A grade is considered acceptable.
        
        Args:
            analysis_result: The result from the vision analysis, expected to contain a grade.
            
        Returns:
            bool: True if the grade is an A; False otherwise.
        """
        try:
            if "GRADE:" in analysis_result:
                grade_line = analysis_result.split("GRADE:")[1].split("\n")[0].strip()
                if not grade_line:
                    logger.error("No grade found after 'GRADE:'")
                    return False
                grade = grade_line[0].upper()  # Take first character as grade
                if grade == "A":
                    return True
                else:
                    logger.info(f"Grade provided is {grade}, which does not meet the required A grade")
                    return False
            # Fallback to legacy YES/NO format if no grade found; legacy responses are not acceptable since only A passes.
            lines = analysis_result.strip().splitlines()
            if lines and lines[0].strip().upper() in ["YES", "NO"]:
                logger.warning("Legacy YES/NO format used, failing because only an A grade is acceptable")
                return False
            return False
        except Exception as e:
            logger.error(f"Error determining grade: {e}")
            return False

    def _check_impl(self, protoblock: ProtoBlock, codebase: str, code_diff: str) -> Union[Tuple[bool, str, str], TrustyAgentResult]:
        """
        Compare the before and after states with the provided reference image.
        
        Args:
            protoblock: The ProtoBlock containing task specifications
            codebase: Dictionary mapping file paths to their contents
            code_diff: The git diff showing implemented changes
            
        Returns:
            TrustyAgentResult: The result with comparison details
        """
        # Create a result object for this agent
        result = TrustyAgentResult(
            success=False,  # Default to False, will set to True if successful
            agent_type="web_reference",
            summary="Checking visual output against reference image"
        )
        
        try:
            # Store the protoblock for use in _capture_state
            self.protoblock = protoblock

            # Retrieve or load the reference image if not already set
            if not self.reference_image or not self.reference_image_path:
                image_url = getattr(protoblock, "image_url", None)
                logger.debug(f"Reference image URL: {image_url}")
                if image_url:
                    self.set_reference_image(image_url)
                if not self.reference_image or not self.reference_image_path:
                    error_msg = "Reference image not provided"
                    result.summary = error_msg
                    result.add_error(error_msg, "Missing reference image")
                    return result
            
            # Add reference image to result
            result.details["reference_image_path"] = self.reference_image_path
            
            # Verify we have the before state
            if not self.before_screenshot_path:
                error_msg = "No initial state captured"
                result.summary = error_msg
                result.add_error(error_msg, "Missing before state")
                return result
            
            # Add before screenshot to result
            result.add_screenshot(
                path=self.before_screenshot_path,
                description="Before state screenshot"
            )
            logger.info(f"Added before screenshot to result: {self.before_screenshot_path}")
            
            # Capture after state
            try:
                self.after_screenshot_path = self._capture_state()
                
                # Add after screenshot to result
                result.add_screenshot(
                    path=self.after_screenshot_path,
                    description="After state screenshot"
                )
                logger.info(f"Added after screenshot to result: {self.after_screenshot_path}")
            except Exception as e:
                error_msg = f"Failed to capture after state: {str(e)}"
                result.summary = error_msg
                result.add_error(error_msg, "Screenshot failed")
                return result
            
            # Create a comparison image with all three images side by side
            # Order: before, after, reference
            try:
                self.comparison_path = os.path.join(
                    os.path.dirname(self.before_screenshot_path),
                    f"comparison_with_reference_{uuid.uuid4()}.png"
                )
                
                comparison_img = stitch_images(
                    self.before_screenshot_path,
                    self.after_screenshot_path,
                    self.reference_image_path,
                    border=10,
                    border_color="black"
                )
                comparison_img.save(self.comparison_path)
                logger.info(f"Comparison with reference image saved: {self.comparison_path}")
                
                # Add comparison to result
                result.add_comparison(
                    before_path=self.before_screenshot_path,
                    after_path=self.after_screenshot_path,
                    description="Before/After/Reference comparison"
                )
                result.details["comparison_path"] = self.comparison_path
            except Exception as e:
                error_msg = f"Failed to create comparison image: {str(e)}"
                result.summary = error_msg
                result.add_error(error_msg, "Comparison failed")
                return result
            
            # Get the expected changes description from the protoblock
            expected_changes = protoblock.trusty_agent_prompts.get("web_reference", "")
            if not expected_changes:
                expected_changes = "Analyze the differences between the before state, after state, and reference image. Assess how closely the after state matches the reference."
            
            result.details["expected_changes"] = expected_changes
            
            # Analyze the comparison image
            try:
                # Create detailed prompt for analysis
                prompt = f"""
                This image shows three visualizations side by side:
                1. LEFT: The BEFORE state (prior to code changes)
                2. MIDDLE: The AFTER state (current implementation)
                3. RIGHT: The REFERENCE image (target visualization)
                
                Task description: {protoblock.task_description}
                Expected changes: {expected_changes}
                
                Please analyze:
                1. How well does the AFTER state (middle) match the REFERENCE image (right)?
                2. What differences exist between the AFTER state and the REFERENCE image?
                3. What improvements were made from the BEFORE state to the AFTER state?
                4. What still needs to be improved to make the AFTER state match the REFERENCE?
                
                Conclude with a letter grade (A-F):
                A: Perfect match, the After state matches the Reference exactly
                B: Very close match with minor differences
                C: Moderate match with noticeable differences
                D: Poor match with significant differences
                F: Failed, minimal similarity to reference
                
                Format your response like this:
                
                ## COMPARISON ANALYSIS
                (Detailed analysis comparing the three images)
                
                ## IMPROVEMENTS IMPLEMENTED
                (What was successfully improved from Before to After)
                
                ## MISSING ELEMENTS
                (What still needs to be implemented/fixed in After to match Reference)
                
                ## GRADE: [A/B/C/D/F]
                (Brief explanation of the grade)
                """
                
                messages = [
                    Message(role="user", content=[
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"file://{self.comparison_path}"}}
                    ])
                ]
                
                self.analysis_result = self.llm_client.chat_completion(messages)
                result.add_report(self.analysis_result, "Reference Comparison Analysis")
            except Exception as e:
                error_msg = f"Failed to analyze comparison: {str(e)}"
                result.summary = error_msg
                result.add_error(error_msg, "Analysis failed")
                return result
            
            # Extract grade if present
            grade = None
            if "GRADE:" in self.analysis_result:
                grade_line = self.analysis_result.split("GRADE:")[1].split("\n")[0].strip()
                if grade_line:
                    grade = grade_line[0].upper()  # Take first character as grade
                    result.add_grade(grade, "A-F", "Graded on visual matching from A (perfect) to F (failed)")
                    
                    # For reference comparisons, only an A is a passing grade
                    is_passing = grade == "A"
                    
                    # Update result success status and summary based on grade
                    if is_passing:
                        result.success = True
                        result.summary = f"Reference comparison passed with grade {grade}"
                    else:
                        result.success = False
                        result.summary = f"Reference comparison failed with grade {grade} (only A grade passes)"
                    
                    return result
            
            # If no grade, default to failure
            result.success = False
            result.summary = "Reference comparison failed - no grade provided by analysis"
            
            return result
            
        except Exception as e:
            logger.exception(f"Error in reference comparison: {str(e)}")
            result.success = False
            result.summary = "Reference comparison exception"
            result.add_error(str(e), "Exception", logger.format_exc() if hasattr(logger, 'format_exc') else None)
            return result
            
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
        
        # If all else fails, return None
        return None 