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
from tac.agents.trusty.results import TrustyAgentResult
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
    prompt_target="coding_agent",
    llm="gpt-4o"
)
class ThreeJSVisionBeforeAfterAgent(ComparativeTrustyAgent):
    """
    A trusty agent that captures screenshots before and after code changes,
    stitches them together side by side, and analyzes the differences.
    """

    def __init__(self):
        logger.info("Initializing ThreeJSVisionBeforeAfterAgent")
        self.llm_client = LLMClient(component="vision")
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

    def _check_impl(self, protoblock: ProtoBlock, codebase: str, code_diff: str) -> Union[Tuple[bool, str, str], TrustyAgentResult]:
        """
        Compare the before and after states.
        
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
            agent_type="threejs_vision_before_after",
            summary="Checking visual changes between before and after states"
        )
        
        try:
            # Store the protoblock for use in _capture_state
            self.protoblock = protoblock
            
            # Verify we have the before state
            if not self.before_screenshot_path:
                result.summary = "No initial state captured"
                result.add_error("Before screenshot not found", "Missing before state")
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
            
            # Verify that screenshots exist and have content
            for img_path, img_name in [(self.before_screenshot_path, "Before"), (self.after_screenshot_path, "After")]:
                if not os.path.exists(img_path):
                    error_msg = f"{img_name} screenshot file not found: {img_path}"
                    result.summary = error_msg
                    result.add_error(error_msg, f"Missing {img_name.lower()} screenshot")
                    return result
                    
                file_size = os.path.getsize(img_path)
                if file_size == 0:
                    error_msg = f"{img_name} screenshot file is empty: {img_path}"
                    result.summary = error_msg
                    result.add_error(error_msg, f"Empty {img_name.lower()} screenshot")
                    return result
                
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
            
            # Add comparison to result
            result.add_comparison(
                before_path=self.before_screenshot_path,
                after_path=self.after_screenshot_path,
                description="Before and after comparison"
            )
            result.details["comparison_path"] = self.comparison_path
            logger.info(f"Added comparison path to result details: {self.comparison_path}")
            
            # Verify the comparison image was created properly
            if not os.path.exists(self.comparison_path):
                error_msg = "Failed to create comparison image"
                result.summary = error_msg
                result.add_error(error_msg, "Image stitching failed")
                return result
                
            comparison_file_size = os.path.getsize(self.comparison_path)
            if comparison_file_size == 0:
                error_msg = "Comparison image file is empty"
                result.summary = error_msg 
                result.add_error(error_msg, "Empty comparison image")
                return result
                
            logger.info(f"Comparison image verified: {self.comparison_path} ({comparison_file_size} bytes)")
            
            # Clean up the temporary dummy image file.
            os.unlink(dummy_image_path)
            
            # Get expected changes from protoblock
            expected_changes = protoblock.trusty_agent_prompts.get("threejs_vision_before_after", "")
            if not expected_changes:
                expected_changes = "Analyze the visual differences between the before and after states."
            
            # Add expected changes to result details
            result.details["expected_changes"] = expected_changes
            

            self.analysis_result = self.analyze_comparison(self.comparison_path, expected_changes)
            
            # Add analysis to result
            result.add_report(self.analysis_result, "Visual Analysis")
            
            # Extract grade from analysis if available
            grade = None
            grade_scale = "A-F"
            if "GRADE:" in self.analysis_result:
                grade_line = self.analysis_result.split("GRADE:")[1].split("\n")[0].strip()
                if grade_line:
                    grade = grade_line[0].upper()  # Take first character as grade
                    result.add_grade(grade, grade_scale, f"Graded on scale from A (best) to F (worst)")
            
            # Log the detailed analysis
            logger.info(f"Visual comparison analysis:\n{self.analysis_result}")
            
            # Determine success based on grade or content analysis
            minimum_grade = config.general.trusty_agents.minimum_vision_score.upper()
            success = determine_vision_success(self.analysis_result, minimum_grade) 
            
            if success:
                result.success = True
                result.summary = "Visual comparison successful"
                if grade:
                    result.summary += f" with grade {grade}"
                return result
            else:
                result.success = False
                result.summary = "Visual comparison failed"
                if grade:
                    result.summary += f" with grade {grade}"
                return result
            
        except Exception as e:
            logger.exception(f"Error in visual comparison: {str(e)}")
            result.success = False
            result.summary = "Visual comparison error"
            result.add_error(str(e), "Visual comparison error", logger.format_exc() if hasattr(logger, 'format_exc') else None)
            return result
            
        finally:
            # Clean up browser resources
            self._cleanup_browser()

    def analyze_comparison(self, comparison_path: str, expected_changes: str) -> str:
                    # Create a detailed prompt for analysis
            prompt = f"""You are a visual expert analyzes comparative screenshots of a threejs application. The before state of the application is on the left and the after state is on the right. You will need to compare the left (before) to the right (after) and provide a detailed analysis of the changes you see. 
We expect the following changes, here are the expected changes: {expected_changes}
            
We want the following output format:
DIFFERENCES BEFORE VS AFTER:
(Extensive list the differences you see between the before and after screenshots)

ACCURACY OF EXPECTED CHANGES:
(How accurately are the expected changes reflected in the after screenshot, as compared to the before screenshot?)

UNEXPECTED CHANGES:
(Are there any further changes in the after screenshot that were not expected? If so, list them. Cross-check the differences you listed in the DIFFERENCES BEFORE VS AFTER section. with the expected changes.)

GRADE:
(How appropriate would you rate the TOTAL changes, on a scale of A to F? A is the best, F is the worst. 
Your responsibility is to FAIL the test (D or F) if one of two conditions is met: 
-the changes are not accurate with regards to the expected changes
-there are ANY unexpected changes that we did not expect
ONLY RETURN HERE A SINGLE LETTER, A, B, C, D, F)

OUT OF SCOPE REPORT:
(Report here if the expected changes are out of scope of what you can do to judge, given two screenshots)

RECOMMENDATIONS:
(Suggest how the expected changes from the left before image could be implemented better in the right after image)."""
            
            logger.info(f"Analyzing comparison with prompt: {prompt}")
            
            # Sleep to ensure the image is fully written to disk
            time.sleep(0.5)
            
            # Direct call to LLM client for vision analysis to ensure image is passed correctly
            messages = [
                Message(role="user", content=prompt),
            ]
            
            # Use vision_chat_completion with the comparison image path
            logger.info(f"Sending comparison image to vision model: {self.comparison_path}")
            

            analysis_result = self.llm_client.vision_chat_completion(messages, self.comparison_path)

            return analysis_result

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

if __name__ == "__main__":
    # Example of using the ThreeJSVisionBeforeAfterAgent with an existing image
    agent = ThreeJSVisionBeforeAfterAgent()
    
    # Existing comparison image to analyze
    comparison_image = "/Users/jjj/Downloads/comparison_bb59c33a-f596-4b66-9c37-7dd137582b7e.png"
    
    # Create a simple ProtoBlock with the expected changes
    from tac.blocks import ProtoBlock
    
    # Fix ProtoBlock initialization to match the class definition
    protoblock = ProtoBlock(
        task_description="Analyze starfield visualization",
        write_files=[],
        context_files=[],
        block_id="example_test",
        trusty_agent_prompts={
            "threejs_vision_before_after": "Assert that the star field covers the full screen in the after image."
        }
    )

    expected_changes = protoblock.trusty_agent_prompts.get("threejs_vision_before_after")
    # Set the comparison path and protoblock
    agent.comparison_path = comparison_image
    agent.set_protoblock(protoblock)
    
    # Directly use the _check_impl method with the existing image
    # Provide empty codebase and code_diff since we're just analyzing an image
    result = agent.analyze_comparison(comparison_image, expected_changes)
    
    # Print the result
    print(result)


"""
BACK TO OLD RULE:
how accurate is change there?
is there something else that got changed?
outof scope things mention explicitly.
"""