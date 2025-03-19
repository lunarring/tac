#!/usr/bin/env python3
import os
import sys
import time
import tempfile
import subprocess
import threading
import logging
from typing import Dict, Tuple, Optional, Union, Any
import signal

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager

from tac.core.llm import LLMClient, Message
from tac.blocks import ProtoBlock
from tac.core.config import config
from tac.core.log_config import setup_logging
from tac.trusty_agents.base import TrustyAgent, trusty_agent

logger = setup_logging('tac.trusty_agents.threejs_vision')

@trusty_agent(
    name="threejs_vision",
    description="Use this trusty agent to verify the Three.js application's visual output. It launches a web browser with Selenium, loads the Three.js application, captures a screenshot, and analyzes it to ensure the 3D rendering matches the expectations.",
    protoblock_prompt="Describe the 3D scene you expect to see in the Three.js application. Be specific about visual elements such as shapes, colors, lighting, camera angle, animations, and any UI elements. Detail what a successful rendering would look like and any specific aspects that must be visible to confirm correct implementation.",
    prompt_target="coding_agent"
)
class ThreeJSVisionAgent(TrustyAgent):
    """
    A trusty agent that launches a web browser using Selenium, loads a Three.js application,
    takes a screenshot, and analyzes it using a vision model to verify the 3D rendering.
    """

    def __init__(self):
        logger.info("Initializing ThreeJSVisionAgent")
        self.llm_client = LLMClient(llm_type="vision")
        self.browser_runner = None
        self.screenshot_path = None
        self.analysis_result = None

    def _check_impl(self, protoblock: ProtoBlock, codebase: str, code_diff: str) -> Tuple[bool, str, str]:
        """
        Launch a browser with Selenium, navigate to the Three.js app, take a screenshot, and analyze it.
        
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
        try:
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
            
            # Run the browser and take a screenshot
            logger.info(f"Running browser for: {app_file_path}")
            timeout = config.general.vision_timeout or 20  # Default to 20 seconds
            screenshot_delay = config.general.vision_screenshot_delay or 5  # Default to 5 seconds
            
            logger.info(f"Browser config: timeout={timeout}s, screenshot_delay={screenshot_delay}s")
            self.browser_runner = BrowserRunner(app_file_path, timeout=timeout, screenshot_delay=screenshot_delay)
            logger.info("Starting browser...")
            self.browser_runner.start_browser()
            
            # Wait for the screenshot to be taken
            wait_time = screenshot_delay + 2  # Add buffer time
            logger.info(f"Waiting {wait_time} seconds for screenshot...")
            time.sleep(wait_time)
            
            # Get the screenshot path
            self.screenshot_path = self.browser_runner.get_screenshot_path()
            logger.info(f"Screenshot path: {self.screenshot_path}")
            
            # Add a small delay to ensure the file is fully written to disk
            time.sleep(1)
            
            if not self.screenshot_path:
                logger.error("Screenshot path is None")
                self.browser_runner.stop_browser()
                return False, "Failed to get screenshot path", "Screenshot failed"
                
            if not os.path.exists(self.screenshot_path):
                logger.error(f"Screenshot file does not exist: {self.screenshot_path}")
                self.browser_runner.stop_browser()
                return False, f"Screenshot file not found: {self.screenshot_path}", "Screenshot failed"
                
            file_size = os.path.getsize(self.screenshot_path)
            if file_size == 0:
                logger.error(f"Screenshot file is empty: {self.screenshot_path}")
                self.browser_runner.stop_browser()
                return False, f"Screenshot file is empty: {self.screenshot_path}", "Screenshot failed"
                
            logger.info(f"Screenshot file verified: {self.screenshot_path} ({file_size} bytes)")
            
            # Analyze the screenshot
            logger.info("Analyzing screenshot with vision model...")
            prompt = f"""
            Analyze this screenshot of a Three.js application's output. 
            
            Expected 3D visualization elements: {expected_visual}

            Please verify if the expected visual elements are present in the screenshot.
            Be specific about what you see in the 3D scene and whether it matches the expectations.
            If there are any discrepancies, explain them in detail.
            
            You answer with a clear YES or NO verdict in the first line of response. In case of NO, explain why in the following lines.

            Example:

            YES

            NO
            The 3D cube is not visible, I only see a blank canvas instead.
            """
            
            self.analysis_result = self._analyze_screenshot(prompt)
            logger.info(f"Analysis result: {self.analysis_result}")
            
            # Stop the browser
            self.browser_runner.stop_browser()
            
            # Determine success based on the analysis result
            success = self._determine_success(self.analysis_result)
            
            if success:
                return True, "", ""
            else:
                failure_type = "Three.js visual verification failed"
                error_analysis = f"The Three.js application's visual output did not match expectations:\n\n{self.analysis_result}"
                return False, error_analysis, failure_type
            
        except Exception as e:
            logger.exception(f"Error in Three.js vision testing: {str(e)}")
            if self.browser_runner and self.browser_runner.is_running():
                self.browser_runner.stop_browser()
            return False, f"Error during Three.js vision testing: {str(e)}", "Three.js vision testing exception"

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
            
            # Create messages for the vision model
            vision_messages = [
                Message(role="system", content="You are a helpful assistant that can analyze 3D visualizations created with Three.js"),
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
        Determine if the vision analysis indicates success.
        
        Args:
            analysis_result: The result of the vision analysis
            
        Returns:
            bool: True if the analysis indicates success, False otherwise
        """
        # Check if the result is in the expected format with YES/NO on the first line
        lines = analysis_result.strip().split('\n')
        if lines and lines[0].strip().upper() in ["YES", "NO"]:
            return lines[0].strip().upper() == "YES"
        
        # If not in the expected format, look for positive/negative indicators
        positive_indicators = [
            "matches expectations",
            "matches the expectations",
            "visual elements are present",
            "expected elements are present",
            "successfully displays",
            "correctly displays",
            "correctly implemented",
            "successfully implemented",
            "3d scene looks good",
            "three.js visualization is correct"
        ]
        
        for indicator in positive_indicators:
            if indicator.lower() in analysis_result.lower():
                return True
        
        negative_indicators = [
            "does not match",
            "doesn't match",
            "not match",
            "missing",
            "absent",
            "not present",
            "not found",
            "not visible",
            "cannot see",
            "can't see",
            "failed to display",
            "failed to render",
            "rendering issue",
            "3d elements are missing"
        ]
        
        for indicator in negative_indicators:
            if indicator.lower() in analysis_result.lower():
                return False
        
        # If no clear indicators, default to False
        return False


class BrowserRunner:
    def __init__(self, html_file_path, timeout=None, screenshot_delay=5):
        """
        Initialize the BrowserRunner with the path to the HTML file.
        
        Args:
            html_file_path (str): Path to the HTML file to open
            timeout (int, optional): Timeout in seconds after which the browser will be closed.
                                    None means no timeout (run indefinitely until stopped manually).
            screenshot_delay (int, optional): Delay in seconds before taking a screenshot.
        """
        self.html_file_path = html_file_path
        self.driver = None
        self.running = False
        self.timeout = timeout
        self.timeout_thread = None
        self.screenshot_delay = screenshot_delay
        self.screenshot_thread = None
        self.screenshot_path = None
        
    def start_browser(self):
        """Start the browser with Selenium and navigate to the HTML file"""
        if self.running:
            logger.info("Browser is already running")
            return
        
        try:
            # Setup Chrome options
            chrome_options = Options()
            # Don't run in headless mode to fix visibility issues
            # chrome_options.add_argument("--headless")  # Run in headless mode
            chrome_options.add_argument("--window-size=1920,1080")  # Set window size
            # chrome_options.add_argument("--disable-gpu")  # Disable GPU hardware acceleration
            chrome_options.add_argument("--no-sandbox")  # Bypass OS security model
            chrome_options.add_argument("--disable-dev-shm-usage")  # Overcome limited resource problems
            
            # Create a new Chrome driver
            logger.info("Initializing Chrome WebDriver")
            try:
                # Try using webdriver_manager to install and get the driver
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
            except Exception as e:
                logger.warning(f"Failed to initialize Chrome driver with webdriver_manager: {e}")
                logger.info("Trying alternative initialization method...")
                
                # Try the default Chrome driver path
                self.driver = webdriver.Chrome(options=chrome_options)
                
            logger.info("Chrome WebDriver initialized successfully")
            
            # Convert file path to URL
            file_url = f"file://{os.path.abspath(self.html_file_path)}"
            
            # Navigate to the HTML file
            logger.info(f"Navigating to: {file_url}")
            self.driver.get(file_url)
            
            # Wait for the page to load
            logger.info("Waiting for page to load...")
            self.driver.implicitly_wait(5)  # Wait up to 5 seconds for elements to be available
            
            # Print page title for debugging
            logger.info(f"Page title: {self.driver.title}")
            
            # Try to wait for the THREE global object to be available, which indicates Three.js has loaded
            try:
                WebDriverWait(self.driver, 10).until(
                    lambda d: d.execute_script("return window.hasOwnProperty('THREE') || document.readyState === 'complete'")
                )
                logger.info("Three.js detected or page fully loaded")
                
                # Additional script to check if the THREE.js is initialized properly
                threejs_status = self.driver.execute_script("""
                    try {
                        if (window.THREE) {
                            return {
                                hasThree: true,
                                hasScene: Boolean(document.querySelector('canvas')),
                                hasRenderer: Boolean(window.renderer),
                                hasCamera: Boolean(window.camera),
                                documentReady: document.readyState
                            };
                        } else {
                            return {
                                hasThree: false,
                                documentReady: document.readyState
                            };
                        }
                    } catch(e) {
                        return 'Error: ' + e.message;
                    }
                """)
                logger.info(f"Three.js status: {threejs_status}")
                
            except TimeoutException:
                logger.warning("Timeout waiting for Three.js to load, continuing anyway")
            
            self.running = True
            
            # Start timeout thread if timeout is specified
            if self.timeout is not None:
                self.timeout_thread = threading.Thread(target=self._timeout_monitor)
                self.timeout_thread.daemon = True
                self.timeout_thread.start()
            
            # Start screenshot thread
            self.screenshot_thread = threading.Thread(target=self._take_screenshot_after_delay)
            self.screenshot_thread.daemon = True
            self.screenshot_thread.start()
            
            logger.info(f"Browser started for {self.html_file_path}")
            
        except Exception as e:
            logger.error(f"Error starting browser: {e}")
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
            self.running = False
    
    def _take_screenshot_after_delay(self):
        """Take a screenshot after the specified delay"""
        time.sleep(self.screenshot_delay)
        
        if not self.running or not self.driver:
            logger.info("Browser is no longer running, cannot take screenshot")
            return
        
        try:
            # Create a temporary file for the screenshot
            fd, self.screenshot_path = tempfile.mkstemp(suffix='.png')
            os.close(fd)
            
            # Wait for any animations or resources to load
            logger.info("Taking screenshot of Three.js application")
            
            # Additional wait to ensure Three.js scene is fully rendered
            try:
                # Execute JavaScript to check if Three.js renderer exists and has rendered at least one frame
                WebDriverWait(self.driver, 10).until(
                    lambda d: d.execute_script("""
                        return window.THREE && 
                               (document.querySelector('canvas') !== null) && 
                               document.readyState === 'complete';
                    """)
                )
                logger.info("Three.js canvas detected")
                # Add a small additional delay to ensure rendering is complete
                time.sleep(2)
            except Exception as e:
                logger.warning(f"Could not verify Three.js rendering: {e}")
                # Add longer delay if we couldn't verify
                time.sleep(5)
            
            # Take the screenshot
            logger.info(f"Taking screenshot and saving to {self.screenshot_path}")
            self.driver.save_screenshot(self.screenshot_path)
            
            # Verify the screenshot was taken
            if os.path.exists(self.screenshot_path) and os.path.getsize(self.screenshot_path) > 0:
                logger.info(f"Screenshot saved to {self.screenshot_path} ({os.path.getsize(self.screenshot_path)} bytes)")
            else:
                logger.error(f"Failed to save screenshot to {self.screenshot_path}")
                
        except Exception as e:
            logger.error(f"Error taking screenshot: {e}")
            
    def get_screenshot_path(self):
        """Get the path to the saved screenshot"""
        return self.screenshot_path
    
    def _timeout_monitor(self):
        """Monitor the timeout and stop the browser when reached"""
        if self.timeout is None:
            return
            
        time.sleep(self.timeout)
        if self.running:
            logger.info(f"Timeout of {self.timeout} seconds reached. Stopping browser...")
            self.stop_browser()
    
    def stop_browser(self):
        """Stop the browser"""
        if not self.running:
            logger.info("No browser is running")
            return
        
        try:
            logger.info("Stopping browser...")
            if self.driver:
                self.driver.quit()
            
            self.running = False
            logger.info("Browser stopped")
            
        except Exception as e:
            logger.error(f"Error stopping browser: {e}")
    
    def is_running(self):
        """Check if the browser is currently running"""
        return self.running


def main():
    """Main function to demonstrate usage"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Run Three.js Vision Testing')
    parser.add_argument('--html_file', default='index.html', 
                       help='Path to the HTML file with Three.js content')
    parser.add_argument('--timeout', type=int, default=30, help='Timeout in seconds (default: 30)')
    parser.add_argument('--delay', type=int, default=8, help='Screenshot delay in seconds (default: 8)')
    
    args = parser.parse_args()
    
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
    
    # Create a dummy ProtoBlock
    class DummyProtoBlock:
        def __init__(self, html_file):
            self.block_id = "test"
            self.write_files = [html_file]
            self.context_files = []
            self._trusty_agent_prompts = {
                "threejs_vision": "A green wireframe cube should be visible in the 3D scene. The cube should be clearly rendered with visible edges and proper lighting. The scene should have a dark background to make the green wireframe stand out."
            }
            
        @property
        def trusty_agent_prompts(self):
            return self._trusty_agent_prompts
    
    print(f"Testing Three.js vision agent with {html_file}")
    print(f"Looking for a green wireframe cube...")
    print(f"Timeout: {args.timeout} seconds, Screenshot delay: {args.delay} seconds")
    
    # Initialize the agent
    agent = ThreeJSVisionAgent()
    
    # Set the config values before agent initialization
    config.general.vision_timeout = args.timeout
    config.general.vision_screenshot_delay = args.delay
    
    # Run the check directly using the agent's method
    protoblock = DummyProtoBlock(html_file)
    try:
        codebase = open(html_file, 'r').read()
        print(f"Successfully read HTML file: {html_file} ({len(codebase)} bytes)")
    except Exception as e:
        print(f"Error reading HTML file: {str(e)}")
        codebase = ""
    
    code_diff = ""
    
    try:
        # Run the actual check
        print("Starting browser and taking screenshot...")
        success, error_analysis, failure_type = agent._check_impl(protoblock, codebase, code_diff)
        
        # Display results
        print("\nTest Results:")
        print(f"Success: {success}")
        
        if not success:
            print(f"Failure Type: {failure_type}")
            print("\nError Analysis:")
            print(error_analysis)
        else:
            print("\nSuccess! The green wireframe cube was verified.")
        
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
    finally:
        # Ensure browser is stopped
        if agent.browser_runner and agent.browser_runner.is_running():
            print("Stopping browser...")
            agent.browser_runner.stop_browser()
    
    print("Done!")


if __name__ == "__main__":
    main() 