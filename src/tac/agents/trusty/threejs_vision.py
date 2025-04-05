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

logger = setup_logging('tac.trusty_agents.threejs_vision')

@trusty_agent(
    name="threejs_vision",
    description="Use this trusty agent to verify the visual output of web applications IN CASE there is no visual comparison from a previous version available! For instance, if considering something where we don't have a base version and do it from scratch, use this agent. Otherwise use threejs_vision_before_after or threejs_vision_reference. Otherwise, use it for anything visual with web content like html, threejs, or webgl.",
    protoblock_prompt="For this visual test, you describe the 3D scene you expect to see. Describe the visual elements such as shapes, colors, lighting, camera angle etc. Don't describe code changes, only describe what can be SEEN by LOOKING at the scene. The idea is that given an image of the scene and this description of yours, someone should be able to tell if the scene is correct or not. Directly describe the scene and what to expect.",
    prompt_target="coding_agent"
)
class ThreeJSVisionAgent(TrustyAgent):
    """
    A trusty agent that launches a web browser using Playwright, loads a Three.js application,
    takes a screenshot, and analyzes it using a vision model to verify the 3D rendering.
    """

    def __init__(self):
        logger.info("Initializing ThreeJSVisionAgent")
        self.llm_client = LLMClient(llm_type="vision")
        self.screenshot_path = None
        self.analysis_result = None
        self.error_analyzer = ErrorAnalyzer()
        self.collected_errors = []  # Initialize collected_errors list

    def _check_impl(self, protoblock: ProtoBlock, codebase: str, code_diff: str) -> Tuple[bool, str, str]:
        """
        Launch a browser with Playwright, navigate to the Three.js app, take a screenshot, and analyze it.
        """
        playwright = None
        browser = None
        context = None
        page = None
        
        try:
            logger.info("========== STARTING NEW THREEJS VISUAL TEST ==========")
            
            # Get the HTML file path
            app_file_path = self._get_app_file_path(protoblock)
            if not app_file_path:
                return False, "Could not determine which HTML file to run", "No HTML file found"
            
            if not os.path.exists(app_file_path):
                return False, f"HTML file not found: {app_file_path}", "HTML file not found"
            
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
                return False, f"Failed to load page: {response.status if response else 'No response'}", "Browser errors detected"
            
            # Verify page load
            success, errors, _ = verify_page_load(page, timeout=30000)
            if not success:
                return False, "\n".join(errors), "Browser errors detected"
            
            # Take screenshot
            try:
                self.screenshot_path = take_page_screenshot(page)
                logger.info(f"Screenshot saved: {self.screenshot_path}")
            except Exception as e:
                return False, f"Failed to take screenshot: {str(e)}", "Screenshot failed"
            
            # Get expected visual elements
            expected_visual = protoblock.trusty_agent_prompts.get("threejs_vision", "")
            if not expected_visual:
                expected_visual = "Analyze what you see in the 3D scene and describe the Three.js visualization in detail."
            
            # Analyze screenshot
            prompt = f"Analyze this screenshot of a Three.js application's output. Expected: {expected_visual}"
            self.analysis_result = analyze_screenshot(self.screenshot_path, prompt, self.llm_client)
            
            # Determine success
            success = determine_vision_success(self.analysis_result, config.general.trusty_agents.minimum_vision_score.upper())
            
            if success:
                return True, "", ""
            else:
                return False, self.analysis_result, "Three.js visual verification failed"
            
        except Exception as e:
            logger.exception(f"Error in Three.js vision testing: {str(e)}")
            return False, str(e), "Three.js vision testing exception"
            
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
                
            logger.info(f"Screenshot file verified: {self.screenshot_path} ({file_size} bytes)")
            
            # Create messages for the vision model with updated star rating system
            vision_messages = [
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
            
            # Use vision_chat_completion with the screenshot path
            logger.info(f"Sending image to vision model: {self.screenshot_path}")
            response_vision = self.llm_client.vision_chat_completion(vision_messages, self.screenshot_path)
            return response_vision
        except Exception as e:
            logger.exception(f"Error during vision analysis: {str(e)}")
            return f"Vision analysis failed: {str(e)}"

    def _determine_success(self, analysis_result: str) -> bool:
        """
        Determine if the vision analysis indicates success based on the star rating.
        
        Args:
            analysis_result: The result of the vision analysis
            
        Returns:
            bool: True if the star rating meets or exceeds the minimum required rating from config
        """
        try:
            # Get minimum passing star rating from config
            min_stars = config.general.trusty_agents.minimum_vision_score
            
            # Extract star rating from the analysis
            if "STAR RATING:" in analysis_result:
                rating_line = analysis_result.split("STAR RATING:")[1].split("\n")[0].strip()
                
                # Clean up any markdown formatting (e.g., ** for bold)
                rating_line = rating_line.replace("*", "")
                
                # Try to extract a number from the line
                import re
                numbers = re.findall(r'\d+\.?\d*', rating_line)
                if numbers:
                    try:
                        stars = float(numbers[0])
                        # Ensure the rating is within bounds
                        stars = max(0.0, min(5.0, stars))
                        
                        # Store the star rating for UI display
                        self.stars = stars
                        self.grade = f"{stars:.1f}"
                        
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
                        
                        # Compare star ratings
                        return stars >= min_stars
                    except (ValueError, IndexError):
                        logger.error(f"Failed to parse star rating from: {rating_line}")
                        return False
                else:
                    logger.error(f"No numeric rating found in: {rating_line}")
                    return False
            
            # Fallback to old YES/NO format if no rating found
            lines = analysis_result.strip().split('\n')
            if lines and lines[0].strip().upper() in ["YES", "NO"]:
                logger.warning("Using legacy YES/NO format - treating YES as 4.0 stars and NO as 0.0 stars")
                answer = lines[0].strip().upper() == "YES"
                self.stars = 4.0 if answer else 0.0
                self.grade = "4.0" if answer else "0.0"
                self.grade_info = "Legacy YES format" if answer else "Legacy NO format"
                return answer
            
            return False
            
        except Exception as e:
            logger.error(f"Error determining success from star rating: {e}")
            return False


def main():
    """Main function to demonstrate usage"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Run Three.js Vision Testing')
    parser.add_argument('--html_file', default='index.html', 
                       help='Path to the HTML file with Three.js content')
    parser.add_argument('--timeout', type=int, default=10, help='Timeout in seconds (default: 10)')
    parser.add_argument('--delay', type=int, default=3, help='Screenshot delay in seconds (default: 3)')
    
    args = parser.parse_args()
    
    # Check if Playwright is available and installed
    if not ensure_playwright_installed():
        return
    
    html_file = args.html_file
    
    # Check if the HTML file exists
    if not os.path.exists(html_file):
        print(f"Error: HTML file not found at {html_file}")
        print(f"Current working directory: {os.getcwd()}")
        print("Available files in current directory:")
        for file in os.listdir('.'):
            if file.endswith('.html'):
                print(f" - {file}")
        return
    
    # Print configuration messages
    print(f"Testing Three.js vision agent with {html_file}")
    print(f"Timeout: {args.timeout} seconds, Screenshot delay: {args.delay} seconds")
    print("Mode: Headless")
    print("Engine: Playwright")
    
    if platform.system() == 'Darwin':
        print("NOTE: Using specialized WebGL settings for macOS headless mode")
    
    # Create a dummy ProtoBlock
    class DummyProtoBlock:
        def __init__(self, html_file):
            self.block_id = "test"
            self.write_files = [html_file]
            self.context_files = []
            self.task_description = "Visual test of Three.js scene"
            self._trusty_agent_prompts = {
                "threejs_vision": " Review the updated Three.js scene ensuring that there is one cube rendered above a water surface."
            }
            
        @property
        def trusty_agent_prompts(self):
            return self._trusty_agent_prompts
    
    # Initialize the agent
    agent = ThreeJSVisionAgent()
    
    # Set the config values before agent initialization
    config.general.trusty_agents.vision_timeout = args.timeout
    config.general.trusty_agents.vision_screenshot_delay = args.delay
    
    # Run the check directly using the agent's method
    protoblock = DummyProtoBlock(html_file)
    
    # Print prompt text after protoblock creation
    prompt_text = protoblock.trusty_agent_prompts.get('threejs_vision', '').strip()
    if prompt_text:
        print(f"Checking: {prompt_text[:70]}...")
    else:
        print(f"Checking Three.js scene rendering...")
    
    try:
        # Run the actual check
        print("Starting browser and taking screenshot...")
        success, error_analysis, failure_type = agent._check_impl(protoblock, "", "")
        
        # Display results
        print("\nTest Results:")
        print(f"Success: {success}")
        
        if not success:
            print(f"Failure Type: {failure_type}")
            print("\nError Analysis:")
            print(error_analysis)
        else:
            # Get a more specific success message from the protoblock prompt
            prompt_text = protoblock.trusty_agent_prompts.get('threejs_vision', '').strip()
            if prompt_text:
                success_message = f"Success! The Three.js scene was verified: {prompt_text[:50]}..."
            else:
                success_message = "Success! The Three.js scene was verified."
            print(f"\n{success_message}")
        
        # Print the screenshot path
        if agent.screenshot_path:
            print("\nScreenshot saved to:", agent.screenshot_path)
            file_size = os.path.getsize(agent.screenshot_path) if os.path.exists(agent.screenshot_path) else 0
            print(f"Screenshot size: {file_size} bytes")
            
            # Show more details if available
            if agent.analysis_result:
                print("\nDetailed analysis:")
                print("-" * 50)
                print(agent.analysis_result)
                print("-" * 50)
                
    except Exception as e:
        print(f"Error running test: {str(e)}")
        import traceback
        traceback.print_exc()
    
    print("Done!")


if __name__ == "__main__":
    main()
else:
    # This ensures the agent is only registered once when imported
    __all__ = ["ThreeJSVisionAgent"] 