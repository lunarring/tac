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
from tac.agents.trusty.base import TrustyAgent, trusty_agent
from tac.agents.trusty.pytest import ErrorAnalyzer
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

logger = setup_logging('tac.trusty_agents.web_simple')

@trusty_agent(
    name="web_simple",
    description="Use this trusty agent to verify the visual output of web applications IN CASE we are starting the GUI part from scratch. For instance, if considering something where we don't have a base version and do it from scratch, use this agent. Otherwise, if we already DO have GUI code, it is better to use another trusty agent like web_compare or web_reference. Otherwise, use it for anything visual with web content like html, threejs, or webgl.",
    protoblock_prompt="For this visual test, you describe the scene you expect to see. Describe the visual elements such as shapes, colors, lighting, camera angle etc. Don't describe code changes, only describe what can be SEEN by LOOKING at the scene. The idea is that given an image of the scene and this description of yours, someone should be able to tell if the scene is correct or not. Directly describe the scene and what to expect.",
    prompt_target="coding_agent",
    llm="gpt-4o"
)
class WebSimpleAgent(TrustyAgent):
    """
    A trusty agent that launches a web browser using Playwright, loads a web application,
    takes a screenshot, and analyzes it using a vision model to verify the rendering.
    """

    def __init__(self):
        logger.info("Initializing WebSimpleAgent")
        self.llm_client = LLMClient(component="vision")
        self.screenshot_path = None
        self.analysis_result = None
        self.error_analyzer = ErrorAnalyzer()
        self.collected_errors = []  # Initialize collected_errors list

    def _check_impl(self, protoblock: ProtoBlock, codebase: str, code_diff: str) -> Union[Tuple[bool, str, str], TrustyAgentResult]:
        """
        Launch a browser with Playwright, navigate to the web app, take a screenshot, and analyze it.
        
        Returns:
            TrustyAgentResult: The result of the visual check with screenshot and analysis
        """
        playwright = None
        browser = None
        context = None
        page = None
        
        # Create a result object for this agent
        result = TrustyAgentResult(
            success=False,  # Default to False, will set to True if successful
            agent_type="web_simple",
            summary="Checking visual output of web application"
        )
        
        try:
            logger.info("========== STARTING NEW WEB VISUAL TEST ==========")
            
            # Get the HTML file path
            app_file_path = self._get_app_file_path(protoblock)
            if not app_file_path:
                result.summary = "Could not determine which HTML file to run"
                result.add_error("No HTML file found", "Missing file")
                return result
            
            if not os.path.exists(app_file_path):
                result.summary = f"HTML file not found: {app_file_path}"
                result.add_error(f"HTML file not found: {app_file_path}", "Missing file")
                return result
            
            # Add file info to result details
            result.details["app_file_path"] = app_file_path
            
            # Launch browser and navigate
            playwright = sync_playwright().start()
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            
            # Navigate to URL
            file_url = f"file://{os.path.abspath(app_file_path)}"
            logger.info(f"Navigating to: {file_url}")
            response = page.goto(file_url, wait_until="networkidle", timeout=30000)
            if not response or not response.ok:
                error_msg = f"Failed to load page: {response.status if response else 'No response'}"
                result.summary = error_msg
                result.add_error(error_msg, "Browser error")
                return result
            
            # Verify page load
            success, errors, _ = verify_page_load(page, timeout=30000)
            if not success:
                error_msg = "\n".join(errors)
                result.summary = "Browser errors detected"
                result.add_error(error_msg, "Browser errors")
                return result
            
            # Take screenshot
            try:
                self.screenshot_path = take_page_screenshot(page)
                logger.info(f"Screenshot saved: {self.screenshot_path}")
                result.add_screenshot(
                    path=self.screenshot_path,
                    description="Web application output"
                )
                result.details["screenshot_path"] = self.screenshot_path
            except Exception as e:
                error_msg = f"Failed to take screenshot: {str(e)}"
                result.summary = error_msg
                result.add_error(error_msg, "Screenshot failed")
                return result
            
            # Get expected visual elements
            expected_visual = protoblock.trusty_agent_prompts.get("web_simple", "")
            if not expected_visual:
                expected_visual = "Analyze what you see in the scene and describe the web visualization in detail."
            
            # Add expected visual to result details
            result.details["expected_visual"] = expected_visual
            
            # Analyze screenshot
            prompt = f"Analyze this screenshot of a web application's output. Expected: {expected_visual}"
            self.analysis_result = analyze_screenshot(self.screenshot_path, prompt, self.llm_client)
            
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
            
            # Determine success based on grade or content analysis
            success = determine_vision_success(self.analysis_result, config.general.trusty_agents.minimum_vision_score.upper())
            
            if success:
                result.success = True
                result.summary = "Visual verification successful"
                return result
            else:
                result.success = False
                result.summary = "Web visual verification failed"
                
                # If we have a grade, add it to the failure message
                if grade:
                    result.summary += f" with grade {grade}"
                    
                return result
            
        except Exception as e:
            logger.exception(f"Error in web vision testing: {str(e)}")
            result.success = False
            result.summary = "Web vision testing exception"
            result.add_error(str(e), "Exception", logger.format_exc() if hasattr(logger, 'format_exc') else None)
            return result
            
        finally:
            # Clean up resources in reverse order
            if context:
                try:
                    context.close()
                except Exception as e:
                    logger.error(f"Error closing context: {e}")
                    
            if browser:
                try:
                    browser.close()
                except Exception as e:
                    logger.error(f"Error closing browser: {e}")
                    
            if playwright:
                try:
                    playwright.stop()
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
        
        # If all else fails, return None
        return None

    def _analyze_screenshot(self, prompt: str) -> str:
        """
        Analyze a screenshot using the vision model.
        
        Args:
            prompt: The prompt to send to the vision model
            
        Returns:
            str: The content of the model's response message
        """
        # Sleep 2 sec so the screenshot is fully written to disk
        time.sleep(2)
        try:
            # Verify the image file exists and has content
            if not self.screenshot_path or not os.path.exists(self.screenshot_path):
                error_msg = f"Screenshot file not found: {self.screenshot_path}"
                logger.error(error_msg)
                return f"Vision analysis failed: {error_msg}"
                
            file_size = os.path.getsize(self.screenshot_path)
            if file_size == 0:
                error_msg = f"Screenshot file is empty: {self.screenshot_path}"
                logger.error(error_msg)
                return f"Vision analysis failed: {error_msg}"
            
            logger.info(f"Analyzing screenshot with vision model. Screenshot size: {file_size} bytes")
            
            # Split the prompt if it's too long
            if len(prompt) > 1000:
                prompt = prompt[:997] + "..."
            
            try:
                messages = [
                    Message(role="user", content=[
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"file://{self.screenshot_path}"}}
                    ])
                ]
                
                response = self.llm_client.chat_completion(messages)
                if not response:
                    return "Vision model returned an empty response."
                
                logger.info(f"Vision analysis complete. Response length: {len(response)}")
                return response
                
            except Exception as e:
                error_msg = f"Error calling vision model: {str(e)}"
                logger.exception(error_msg)
                return f"Vision analysis failed: {error_msg}"
                
        except Exception as e:
            logger.exception(f"Error in screenshot analysis: {str(e)}")
            return f"Vision analysis failed: {str(e)}"

    def _determine_success(self, analysis_result: str) -> bool:
        """
        Determine if the analysis indicates success based on analysis content.
        
        Args:
            analysis_result: The result from the vision analysis
            
        Returns:
            bool: True if the analysis suggests a successful implementation, False otherwise
        """
        try:
            if not analysis_result:
                logger.error("Empty analysis result")
                return False
            
            if "GRADE:" in analysis_result:
                grade_line = analysis_result.split("GRADE:")[1].split("\n")[0].strip()
                if not grade_line:
                    logger.error("No grade found after 'GRADE:'")
                    return False
                grade = grade_line[0].upper()  # Take first character as grade
                # Grades A, B, C are passing
                if grade in ["A", "B", "C"]:
                    return True
                else:
                    logger.info(f"Grade provided is {grade}, which is not passing (A, B, or C)")
                    return False
            
            # Fallback to legacy YES/NO format if no grade found
            lines = analysis_result.strip().splitlines()
            if not lines:
                logger.error("No lines found in analysis result")
                return False
            
            first_line = lines[0].strip().upper()
            if first_line == "YES":
                return True
            elif first_line == "NO":
                return False
            
            # If not in expected format, default to False (failed)
            logger.info(f"Analysis result is not in expected format. First line: '{first_line}'. Failing verification.")
            return False
            
        except Exception as e:
            logger.exception(f"Error determining success from analysis: {str(e)}")
            return False

def main():
    """Command-line entry point for standalone testing."""
    try:
        if not PLAYWRIGHT_AVAILABLE:
            print("Playwright is required for this agent.")
            ensure_playwright_installed()
            return
        
        if len(sys.argv) < 2:
            print("Usage: python web_simple.py <html_file_path>")
            return
        
        html_file = sys.argv[1]
        if not os.path.exists(html_file):
            print(f"File not found: {html_file}")
            return
        
        agent = WebSimpleAgent()
        
        # Create a dummy ProtoBlock for testing
        class DummyProtoBlock:
            def __init__(self, html_file):
                self.write_files = [html_file]
                self.context_files = []
                self.block_id = "test_block"
                self._trusty_agent_prompts = {
                    "web_simple": "Describe what you see in the web visualization."
                }
            
            @property
            def trusty_agent_prompts(self):
                return self._trusty_agent_prompts
        
        protoblock = DummyProtoBlock(html_file)
        
        # Run the agent
        result = agent._check_impl(protoblock, {}, "")
        
        if isinstance(result, TrustyAgentResult):
            print(f"Success: {result.success}")
            print(f"Summary: {result.summary}")
            if result.reports:
                print("\nVisual Analysis:")
                print(result.reports[0].content[:500] + "..." if len(result.reports[0].content) > 500 else result.reports[0].content)
        else:
            success, message, details = result
            print(f"Success: {success}")
            print(f"Message: {message}")
            print(f"Details: {details}")
        
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 