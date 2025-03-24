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
from tac.trusty_agents.base import TrustyAgent, trusty_agent
from tac.trusty_agents.pytest import ErrorAnalyzer
from tac.utils.web_utils import (
    verify_page_load, 
    take_threejs_screenshot,
    generate_unique_screenshot_path,
    analyze_screenshot,
    determine_vision_success
)

logger = setup_logging('tac.trusty_agents.threejs_vision')

# Check if Playwright is installed
PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
    logger.info("Playwright is available for WebGL screenshot support")
except ImportError:
    logger.error("Playwright not found. Cannot take screenshots.")
    logger.error("Install Playwright: pip install playwright")
    logger.error("Then: playwright install chromium")

@trusty_agent(
    name="threejs_vision",
    description="Use this trusty agent to verify the visual output of web applications. Use it for anything visual with web content like html, threejs, or webgl.",
    protoblock_prompt="For this visual test, you describe the 3D scene you expect to see. Describe the visual elements such as shapes, colors, lighting, camera angle etc. Don't describe code changes, only describe what can be SEEN by LOOKING at the scene. The idea is that given an image of the scene and this description of yours, someone should be able to tell if the scene is correct or not.",
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

    def _check_impl(self, protoblock: ProtoBlock, codebase: str, code_diff: str) -> Tuple[bool, str, str]:
        """
        Launch a browser with Playwright, navigate to the Three.js app, take a screenshot, and analyze it.
        
        Args:
            protoblock: The ProtoBlock containing task specifications
            codebase: Summary string of the codebase 
            code_diff: The git diff showing implemented changes
            
        Returns:
            Tuple containing:
            - bool: Success status (True if visual verification passed, False otherwise)
            - str: Error analysis (empty string if success is True)
            - str: Failure type description (empty string if success is True)
        """
        collected_errors = []
        try:
            logger.info("========== STARTING NEW THREEJS VISUAL TEST ==========")
            logger.info(f"Test initiated at {time.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Get the HTML file path to run from the protoblock directly
            app_file_path = self._get_app_file_path(protoblock)
            if not app_file_path:
                return False, "Could not determine which HTML file to run", "No HTML file found"
            
            if not os.path.exists(app_file_path):
                return False, f"HTML file not found: {app_file_path}", "HTML file not found"
            
            # Get the expected visual elements from the protoblock
            expected_visual = protoblock.trusty_agent_prompts.get("threejs_vision", "")
            if not expected_visual:
                logger.warning("No threejs_vision prompt found in protoblock")
                expected_visual = "Analyze what you see in the 3D scene and describe the Three.js visualization in detail."
            
            # Create a temporary file for the screenshot
            self.screenshot_path = generate_unique_screenshot_path()
            file_url = f"file://{os.path.abspath(app_file_path)}"
            
            # First verify the page loads correctly
            success, errors, page = verify_page_load(file_url, timeout=30000)
            if not success:
                self.collected_errors.extend(errors)
                error_analysis = self.error_analyzer.analyze_failure(
                    protoblock,
                    "\n".join(self.collected_errors),
                    codebase
                )
                return False, error_analysis, "Browser errors detected"
            
            # Take Three.js screenshot
            logger.info("Taking Three.js screenshot...")
            try:
                self.screenshot_path = take_threejs_screenshot(page)
                logger.info(f"Three.js screenshot saved: {self.screenshot_path}")
            except Exception as e:
                logger.error(f"Error taking Three.js screenshot: {e}")
                error_analysis = self.error_analyzer.analyze_failure(
                    protoblock,
                    f"Failed to take screenshot: {str(e)}",
                    codebase
                )
                return False, error_analysis, "Screenshot failed"
            
            # Analyze the screenshot
            logger.info("Analyzing screenshot with vision model...")
            prompt = f"""
            Analyze this screenshot of a Three.js application's output. 
            
            Expected 3D visualization elements: {expected_visual}

            Please grade the visualization on a scale from A to F and provide a detailed analysis.
            
            Remember:
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
            (Suggestions for improvement if needed)
            """
            
            self.analysis_result = analyze_screenshot(self.screenshot_path, prompt, self.llm_client)
            # Format the prompt for logging (outside the f-string)
            formatted_prompt = prompt.strip().replace('\n', ' ')
            logger.info(f"Analysis result: {self.analysis_result} (for prompt: {formatted_prompt})")
            
            # Determine success based on the analysis result
            success = determine_vision_success(self.analysis_result, config.general.trusty_agents.minimum_vision_score.upper())
            
            if success:
                return True, "", ""
            else:
                failure_type = "Three.js visual verification failed"
                error_analysis = f"The Three.js application's visual output did not meet minimum requirements:\n\n{self.analysis_result}"
                return False, error_analysis, failure_type
            
        except Exception as e:
            logger.exception(f"Error in Three.js vision testing: {str(e)}")
            collected_errors.append(str(e))
            
            # Use error analyzer to analyze the collected errors
            error_analysis = self.error_analyzer.analyze_failure(
                protoblock,
                "\n".join(collected_errors),
                codebase
            )
            
            return False, error_analysis, "Three.js vision testing exception"

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
            
            # Create messages for the vision model with updated grading system
            vision_messages = [
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
            
            # Use vision_chat_completion with the screenshot path
            logger.info(f"Sending image to vision model: {self.screenshot_path}")
            response_vision = self.llm_client.vision_chat_completion(vision_messages, self.screenshot_path)
            return response_vision
        except Exception as e:
            logger.exception(f"Error during vision analysis: {str(e)}")
            return f"Vision analysis failed: {str(e)}"

    def _determine_success(self, analysis_result: str) -> bool:
        """
        Determine if the vision analysis indicates success based on the grade.
        
        Args:
            analysis_result: The result of the vision analysis
            
        Returns:
            bool: True if the grade meets or exceeds the minimum required grade from config
        """
        try:
            # Get minimum passing grade from config
            min_grade = config.general.trusty_agents.minimum_vision_score.upper()
            if min_grade not in {"A", "B", "C", "D", "F"}:
                logger.warning(f"Invalid minimum_vision_score in config: {min_grade}, defaulting to 'B'")
                min_grade = "B"
            
            # Define grade values (A=4, B=3, C=2, D=1, F=0)
            grade_values = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
            min_grade_value = grade_values[min_grade]
            
            # Extract grade from the analysis
            if "GRADE:" in analysis_result:
                grade_line = analysis_result.split("GRADE:")[1].split("\n")[0].strip()
                grade = grade_line[0].upper()  # Take first character as grade
                
                if grade not in grade_values:
                    logger.error(f"Invalid grade found in analysis: {grade}")
                    return False
                
                # Compare grade values
                return grade_values[grade] >= min_grade_value
            
            # Fallback to old YES/NO format if no grade found
            lines = analysis_result.strip().split('\n')
            if lines and lines[0].strip().upper() in ["YES", "NO"]:
                logger.warning("Using legacy YES/NO format - treating YES as grade 'B' and NO as grade 'F'")
                return lines[0].strip().upper() == "YES"
            
            return False
            
        except Exception as e:
            logger.error(f"Error determining success from grade: {e}")
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
    
    # Check if Playwright is available
    if not PLAYWRIGHT_AVAILABLE:
        print("ERROR: Playwright is not installed.")
        print("Install with: pip install playwright")
        print("Then: playwright install chromium")
        return
    
    # Ensure Playwright browsers are installed
    try:
        print("Ensuring Playwright browsers are installed...")
        import subprocess
        import sys
        try:
            # Check if browsers are already installed
            with sync_playwright() as p:
                if p.chromium:
                    print("Playwright browsers already installed")
                else:
                    raise Exception("Playwright browsers not installed")
            
        except Exception as e:
            print(f"Installing Playwright browsers: {e}")
            subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
            print("Playwright browsers installed successfully")
    except Exception as e:
        print(f"Warning: Could not verify or install Playwright browsers: {e}")
        print("If you encounter errors, run 'playwright install chromium' manually")
    
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