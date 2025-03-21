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
import platform
import shutil
import uuid

from playwright.sync_api import sync_playwright

from tac.core.llm import LLMClient, Message
from tac.blocks import ProtoBlock
from tac.core.config import config
from tac.core.log_config import setup_logging
from tac.trusty_agents.base import TrustyAgent, trusty_agent

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
        self.browser_runner = None
        self.screenshot_path = None
        self.analysis_result = None

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
        try:
            logger.info("========== STARTING NEW THREEJS VISUAL TEST ==========")
            logger.info(f"Test initiated at {time.strftime('%Y-%m-%d %H:%M:%S')}")
            # Ensure we're not using cached screenshots by clearing temporary files
            self.screenshot_path = None
            self.analysis_result = None
            
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
            timeout = config.general.trusty_agents.vision_timeout or 15  # Default to 15 seconds
            screenshot_delay = config.general.trusty_agents.vision_screenshot_delay or 3  # Default to 3 seconds
            
            # Create browser runner with the current settings
            self.browser_runner = BrowserRunner(app_file_path, timeout=timeout, 
                                                screenshot_delay=screenshot_delay)
            
            logger.info("Starting browser with Playwright...")
            self.browser_runner.start_browser()
            
            # Get the screenshot path
            self.screenshot_path = self.browser_runner.get_screenshot_path()
            logger.info(f"Screenshot path: {self.screenshot_path}")
            
            # Delay to ensure file is fully written
            time.sleep(1)
            
            # Stop the browser before checking the screenshot - prevents race conditions
            if self.browser_runner and self.browser_runner.is_running():
                self.browser_runner.stop_browser()
            
            # Check if screenshot was captured successfully
            if not self.screenshot_path or not os.path.exists(self.screenshot_path):
                logger.error(f"Screenshot file not found: {self.screenshot_path}")
                return False, "Failed to capture a screenshot", "Screenshot failed"
            
            file_size = os.path.getsize(self.screenshot_path)
            if file_size == 0:
                logger.error(f"Screenshot file is empty: {self.screenshot_path}")
                return False, f"Screenshot file is empty: {self.screenshot_path}", "Screenshot failed"
            
            # Log information about the screenshot
            if hasattr(self.browser_runner, 'threejs_status'):
                threejs_status = self.browser_runner.threejs_status
                logger.info(f"Three.js status captured: {threejs_status}")
            
            logger.info(f"Screenshot file verified: {self.screenshot_path} ({file_size} bytes)")
            
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
            
            self.analysis_result = self._analyze_screenshot(prompt)
            # Format the prompt for logging (outside the f-string)
            formatted_prompt = prompt.strip().replace('\n', ' ')
            logger.info(f"Analysis result: {self.analysis_result} (for prompt: {formatted_prompt})")
            
            # Determine success based on the analysis result
            success = self._determine_success(self.analysis_result)
            
            if success:
                return True, "", ""
            else:
                failure_type = "Three.js visual verification failed"
                error_analysis = f"The Three.js application's visual output did not meet minimum requirements:\n\n{self.analysis_result}"
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

    def _is_blank_screenshot(self, screenshot_path):
        """Check if a screenshot is blank or just black"""
        try:
            from PIL import Image, ImageStat
            with Image.open(screenshot_path) as img:
                # Check if image is black or mostly black
                stat = ImageStat.Stat(img)
                
                # Get image statistics
                is_black = all(x < 20 for x in stat.mean[:3])  # RGB values very low = black
                
                # Sample more pixels to see if there's variation
                sample_pixels = []
                width, height = img.size
                for x in range(0, width, width//20):  # Sample more points
                    for y in range(0, height, height//20):
                        try:
                            sample_pixels.append(img.getpixel((x, y)))
                        except:
                            pass
                
                unique_colors = len(set(sample_pixels))
                std_dev = stat.stddev
                has_variation = any(x > 15 for x in std_dev[:3])  # Check for color variation
                
                logger.info(f"Screenshot check: is_black={is_black}, unique_colors={unique_colors}, std_dev={std_dev[:3]}, has_variation={has_variation}")
                
                # More sophisticated blank detection
                # Only consider it blank if:
                # 1. It's very dark (black) AND
                # 2. It has very few unique colors AND
                # 3. It has very little color variation
                return is_black and unique_colors < 4 and not has_variation
        except Exception as e:
            logger.warning(f"Error checking blank screenshot: {e}")
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
        self.running = False
        self.timeout = timeout
        self.timeout_thread = None
        self.screenshot_delay = screenshot_delay
        self.screenshot_path = None
        self.threejs_status = None
        logger.info("BrowserRunner initialized")
        
    def _generate_unique_screenshot_path(self):
        """Generate a unique path for the screenshot to prevent reusing old screenshots"""
        timestamp = int(time.time())
        unique_id = str(uuid.uuid4())[:8]
        fd, path = tempfile.mkstemp(prefix=f"screenshot_{timestamp}_{unique_id}_", suffix='.png')
        os.close(fd)
        logger.info(f"Generated unique screenshot path: {path}")
        return path
        
    def start_browser(self):
        """Start the browser and navigate to the HTML file"""
        if self.running:
            logger.info("Browser is already running")
            return
        
        try:
            self._start_playwright_no_thread()
            self.running = True
            logger.info(f"Browser started for {self.html_file_path}")
            
        except Exception as e:
            logger.error(f"Error starting browser: {e}")
            self.stop_browser()
            self.running = False

    def _start_playwright_no_thread(self):
        """Start the browser using Playwright - thread-safe implementation"""
        logger.info("Starting browser with Playwright (no-thread mode)")
        
        # Create a temporary file for the screenshot
        self.screenshot_path = self._generate_unique_screenshot_path()
        
        file_url = f"file://{os.path.abspath(self.html_file_path)}"
        logger.info(f"Target URL: {file_url}")
        logger.info(f"Screenshot path: {self.screenshot_path}")
        
        try:
            # Use a with block to ensure proper cleanup
            with sync_playwright() as playwright:
                # Configure launch options with much more aggressive WebGL support
                launch_options = {
                    "headless": True,
                }
                
                # Add extreme WebGL support flags for headless mode
                launch_options["args"] = [
                    "--use-gl=angle",  # Try ANGLE instead of EGL
                    "--use-angle=default",  # Default ANGLE backend
                    "--enable-webgl",
                    "--ignore-gpu-blocklist",
                    "--enable-gpu-rasterization",
                    "--enable-oop-rasterization",
                    "--enable-zero-copy",
                    "--disable-features=IsolateOrigins,site-per-process",
                    "--enable-features=Vulkan",
                    "--force-color-profile=srgb", 
                    "--force-webgl-msaa-sample-count=4",
                    "--force-gpu-mem-available-mb=1024",
                    "--force-max-texture-size=16384",
                    "--no-sandbox",
                    "--disable-background-timer-throttling",
                    "--disable-web-security"
                ]
                
                # Try with Chromium first (best WebGL support)
                try:
                    browser = playwright.chromium.launch(**launch_options)
                except Exception as e:
                    logger.error(f"Failed to launch Chromium browser: {str(e)}")
                    logger.error("Browser launch error details:")
                    logger.error(f"Launch options: {launch_options}")
                    logger.error(f"Platform: {platform.system()} {platform.release()}")
                    logger.error(f"Python version: {sys.version}")
                    raise Exception(f"Browser launch failed: {str(e)}")
                
                # Create context with enhanced browser settings
                try:
                    context = browser.new_context(
                        viewport={"width": 1920, "height": 1080},
                        device_scale_factor=1,
                        is_mobile=False,
                        has_touch=False,
                        locale="en-US",
                        color_scheme="dark",  # Dark scheme for better WebGL visibility
                        forced_colors="none",
                        reduced_motion="no-preference"
                    )
                except Exception as e:
                    logger.error(f"Failed to create browser context: {str(e)}")
                    browser.close()
                    raise Exception(f"Browser context creation failed: {str(e)}")
                
                # Set up error handlers before creating the page
                page = context.new_page()
                
                # Enhanced error logging for page events with better categorization
                def handle_console(msg):
                    if msg.type == "error":
                        logger.error(f"CONSOLE ERROR: {msg.text}")
                        # Check for common critical errors
                        if any(x in msg.text.lower() for x in [
                            "is not defined", "undefined", "cannot read properties",
                            "syntax error", "reference error", "type error"
                        ]):
                            raise Exception(f"Critical JavaScript error detected: {msg.text}")
                    else:
                        logger.debug(f"CONSOLE {msg.type}: {msg.text}")

                def handle_page_error(err):
                    logger.error(f"PAGE ERROR: {err}")
                    # Check for common critical errors
                    if any(x in str(err).lower() for x in [
                        "is not defined", "undefined", "cannot read properties",
                        "syntax error", "reference error", "type error"
                    ]):
                        # Stop the browser and context before raising the exception
                        try:
                            context.close()
                            browser.close()
                        except:
                            pass
                        raise Exception(f"Critical JavaScript error detected: {err}")

                def handle_request_failed(request):
                    error_text = request.failure.get('errorText', 'Unknown error')
                    logger.error(f"REQUEST FAILED: {request.url} - {error_text}")
                    # Only raise for critical resource failures
                    if request.resource_type in ["script", "stylesheet"]:
                        raise Exception(f"Critical resource failed to load: {request.url} - {error_text}")

                page.on("console", handle_console)
                page.on("pageerror", handle_page_error)
                page.on("requestfailed", handle_request_failed)
                
                # Navigate to page and wait for load with enhanced error handling
                try:
                    logger.info(f"Navigating to: {file_url}")
                    resp = page.goto(file_url, wait_until="networkidle", timeout=30000)
                    if not resp:
                        raise Exception("Page navigation failed - no response received")
                    if resp.status >= 400:
                        raise Exception(f"Page navigation failed with status {resp.status}")
                    logger.info(f"Page loaded with status: {resp.status}")

                    # Check for JavaScript errors after page load
                    js_errors = page.evaluate("""() => {
                        const errors = [];
                        if (window.onerror) {
                            const originalOnError = window.onerror;
                            window.onerror = function(msg, url, line, col, error) {
                                errors.push({
                                    message: msg,
                                    url: url,
                                    line: line,
                                    column: col,
                                    error: error ? error.toString() : null,
                                    stack: error ? error.stack : null
                                });
                                return originalOnError.apply(this, arguments);
                            };
                        }
                        return errors;
                    }""")

                    if js_errors:
                        logger.error("JavaScript errors detected after page load:")
                        for error in js_errors:
                            logger.error(f"Error: {error.get('message')}")
                            logger.error(f"Location: {error.get('url')}:{error.get('line')}:{error.get('column')}")
                            if error.get('stack'):
                                logger.error(f"Stack trace:\n{error.get('stack')}")
                        raise Exception("JavaScript errors detected - cannot proceed with visual test")

                except Exception as e:
                    logger.error(f"Page navigation or JavaScript error: {str(e)}")
                    logger.error("Error details:")
                    logger.error(f"URL: {file_url}")
                    logger.error(f"File exists: {os.path.exists(self.html_file_path)}")
                    logger.error(f"File permissions: {oct(os.stat(self.html_file_path).st_mode)[-3:]}")
                    context.close()
                    browser.close()
                    raise Exception(f"Critical error detected: {str(e)}")
                
                # Extended wait for external scripts
                logger.info(f"Waiting {self.screenshot_delay + 2} seconds for page to render...")
                time.sleep(self.screenshot_delay + 2)
                
                # Check if the page loaded properly and if external scripts were loaded
                resources_loaded = page.evaluate("""() => {
                    const scripts = document.querySelectorAll('script[src]');
                    return Array.from(scripts).map(s => ({
                        src: s.src,
                        loaded: s.complete === undefined ? true : s.complete
                    }));
                }""")
                logger.info(f"External resources loaded: {resources_loaded}")
                
                # Check WebGL support status
                webgl_status = page.evaluate("""() => {
                    const canvas = document.createElement('canvas');
                    let webgl2 = null;
                    let webgl1 = null;
                    
                    try {
                        webgl2 = canvas.getContext('webgl2');
                    } catch (e) {}
                    
                    try {
                        webgl1 = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
                    } catch (e) {}
                    
                    return {
                        webgl2Supported: !!webgl2,
                        webgl1Supported: !!webgl1,
                        // Get detailed WebGL capabilities if available
                        capabilities: webgl2 || webgl1 ? {
                            vendor: (webgl2 || webgl1).getParameter((webgl2 || webgl1).VENDOR),
                            renderer: (webgl2 || webgl1).getParameter((webgl2 || webgl1).RENDERER),
                            version: (webgl2 || webgl1).getParameter((webgl2 || webgl1).VERSION),
                            shadingLanguageVersion: (webgl2 || webgl1).getParameter((webgl2 || webgl1).SHADING_LANGUAGE_VERSION),
                            unmaskedVendor: getParameter(webgl2 || webgl1, 0x9245), // UNMASKED_VENDOR_WEBGL
                            unmaskedRenderer: getParameter(webgl2 || webgl1, 0x9246), // UNMASKED_RENDERER_WEBGL
                            maxTextureSize: (webgl2 || webgl1).getParameter((webgl2 || webgl1).MAX_TEXTURE_SIZE)
                        } : null
                    };
                    
                    // Helper to safely get extension parameters
                    function getParameter(gl, param) {
                        try {
                            const ext = gl.getExtension('WEBGL_debug_renderer_info');
                            return ext ? gl.getParameter(param) : null;
                        } catch (e) {
                            return null;
                        }
                    }
                }""")
                logger.info(f"WebGL support status: {webgl_status}")
                
                # Evaluate Three.js status with deeper inspection
                logger.info("Checking Three.js status (enhanced inspection)...")
                threejs_status = page.evaluate("""() => {
                    try {
                        // Check for THREE global object
                        const hasThree = typeof THREE !== 'undefined';
                        
                        // Get the Three.js version if available
                        const threeVersion = hasThree && THREE.REVISION ? THREE.REVISION : null;
                        
                        // Check for canvas elements
                        const canvases = document.querySelectorAll('canvas');
                        const canvasCount = canvases.length;
                        
                        // Create a map of all WebGL contexts from canvases
                        const contexts = Array.from(canvases).map(canvas => {
                            try {
                                // Try to get or create WebGL context
                                let gl = canvas.getContext('webgl2') || 
                                         canvas.getContext('webgl') || 
                                         canvas.getContext('experimental-webgl');
                                         
                                if (!gl && window.createForcedWebGLContext) {
                                    gl = window.createForcedWebGLContext(canvas);
                                }
                                
                                return {
                                    hasContext: !!gl,
                                    isWebGL2: gl && gl instanceof WebGL2RenderingContext,
                                    size: gl ? [canvas.width, canvas.height] : null,
                                    contextLost: canvas.classList.contains('OffscreenCanvas') || !!canvas.isContextLost?.()
                                };
                            } catch (e) {
                                return { error: e.toString() };
                            }
                        });
                        
                        // Get canvas info with more details
                        const canvasInfo = Array.from(canvases).map((canvas, i) => {
                            try {
                                const style = getComputedStyle(canvas);
                                const rect = canvas.getBoundingClientRect();
                                
                                return {
                                    index: i,
                                    id: canvas.id || null,
                                    className: canvas.className || null,
                                    width: canvas.width,
                                    height: canvas.height,
                                    clientWidth: canvas.clientWidth,
                                    clientHeight: canvas.clientHeight,
                                    display: style.display,
                                    visibility: style.visibility,
                                    opacity: style.opacity,
                                    inViewport: rect.top < window.innerHeight && rect.bottom > 0,
                                    empty: isCanvasEmpty(canvas)
                                };
                            } catch (e) {
                                return { index: i, error: e.toString() };
                            }
                        });
                        
                        // Function to check if canvas is empty
                        function isCanvasEmpty(canvas) {
                            try {
                                const ctx = canvas.getContext('2d');
                                if (!ctx) return null; // Can't check with 2D context
                                
                                const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
                                // Check if all pixels are transparent or black
                                for (let i = 0; i < data.length; i += 4) {
                                    // If any pixel is not transparent and not black, canvas is not empty
                                    if (data[i+3] > 0 && (data[i] > 0 || data[i+1] > 0 || data[i+2] > 0)) {
                                        return false;
                                    }
                                }
                                return true;
                            } catch (e) {
                                return null; // Can't determine if canvas is empty
                            }
                        }
                        
                        // Create canvas if needed
                        if (hasThree && canvasCount === 0) {
                            console.log("THREE exists but no canvas found, creating one");
                            const container = document.querySelector('#canvas-container') || document.body;
                            const canvas = document.createElement('canvas');
                            canvas.width = 800;
                            canvas.height = 600;
                            canvas.style.backgroundColor = "#000000";
                            container.appendChild(canvas);
                            
                            canvasInfo.push({
                                index: 0,
                                width: canvas.width,
                                height: canvas.height,
                                display: 'block',
                                created: true
                            });
                        }
                        
                        // Try to find THREE objects in all global properties
                        let rendererProps = [];
                        let sceneProps = [];
                        let cameraProps = [];
                        
                        // Inspect window object for THREE.js objects
                        for (let prop in window) {
                            try {
                                const obj = window[prop];
                                if (obj && typeof obj === 'object') {
                                    // Enhanced detection of Three.js objects
                                    if ((obj.type === 'Scene' || (obj.isScene && obj.isScene === true)) ||
                                        (obj.children && obj.background !== undefined)) {
                                        sceneProps.push(prop);
                                    }
                                    if ((obj.type === 'WebGLRenderer' || 
                                        (obj.domElement && obj.domElement.tagName === 'CANVAS')) ||
                                        (obj.render && obj.setSize && obj.domElement)) {
                                        rendererProps.push(prop);
                                    }
                                    if ((obj.type === 'PerspectiveCamera' || 
                                        (obj.isPerspectiveCamera && obj.isPerspectiveCamera === true)) ||
                                        (obj.aspect && obj.fov && obj.position && obj.lookAt)) {
                                        cameraProps.push(prop);
                                    }
                                }
                            } catch (e) { /* ignore errors when accessing properties */ }
                        }
                        
                        // Collect any WebGL errors
                        const webglErrors = window.webGLDebug ? window.webGLDebug.errors : [];
                        
                        return {
                            hasThree: hasThree,
                            threeVersion: threeVersion,
                            hasScene: Boolean(window.scene || document.querySelector('canvas') || sceneProps.length > 0),
                            hasRenderer: Boolean(window.renderer || rendererProps.length > 0),
                            hasCamera: Boolean(window.camera || cameraProps.length > 0),
                            documentReady: document.readyState,
                            canvasCount: document.querySelectorAll('canvas').length,
                            canvasInfo: canvasInfo,
                            contextStatus: contexts,
                            rendererProps: rendererProps,
                            sceneProps: sceneProps,
                            cameraProps: cameraProps,
                            webglErrors: webglErrors
                        };
                    } catch(e) {
                        return {error: e.message, stack: e.stack};
                    }
                }""")
                logger.info(f"Three.js status: {threejs_status}")
                self.threejs_status = threejs_status
                
                # Execute common Three.js initialization functions
                if 'hasThree' in threejs_status and threejs_status['hasThree'] and not threejs_status.get('hasRenderer'):
                    logger.info("THREE.js is loaded but no renderer found, trying to execute init functions")
                    try:
                        # Try to execute any animations or init functions
                        page.evaluate("""() => {
                            try {
                                // Look for common function names in Three.js applications
                                const commonFuncs = ['init', 'animate', 'render', 'start', 'setup', 'main'];
                                for (let funcName of commonFuncs) {
                                    if (typeof window[funcName] === 'function') {
                                        console.log(`Calling ${funcName} function`);
                                        window[funcName]();
                                        return `Executed ${funcName} function`;
                                    }
                                }
                                
                                // If no common functions, create basic scene
                                return 'No applicable functions found';
                            } catch(e) {
                                return `Error executing init functions: ${e.message}`;
                            }
                        }""")
                    except Exception as e:
                        logger.error(f"Error executing init functions: {e}")
                
                # Create a basic Three.js scene if still no renderer found
                if not threejs_status.get('hasRenderer', False):
                    logger.info("No renderer detected - NOT creating a fallback scene")
                    # We no longer create a fallback scene as it interferes with testing
                    # Instead, we'll let the test fail naturally if the renderer is missing
                    logger.info("If renderer is missing, this likely indicates a problem with the Three.js code")
                
                # Prepare the scene for rendering with more aggressive approach
                logger.info("Preparing scene for rendering...")
                scene_info = page.evaluate("""() => {
                    try {
                        // Resize any existing canvases
                        const canvases = document.querySelectorAll('canvas');
                        canvases.forEach(canvas => {
                            // Ensure canvas is visible
                            if (canvas.style.display === 'none') {
                                canvas.style.display = 'block';
                            }
                            // Ensure canvas has dimensions
                            if (canvas.width === 0 || canvas.height === 0) {
                                canvas.width = Math.max(canvas.clientWidth, 800);
                                canvas.height = Math.max(canvas.clientHeight, 600);
                                console.log(`Resized canvas to ${canvas.width}x${canvas.height}`);
                            }
                        });
                        
                        // Force animation frame to run
                        if (window.requestAnimationFrame) {
                            window.requestAnimationFrame(() => {});
                        }
                        
                        // Try to find renderer, scene, and camera
                        let rendererFound = false;
                        
                        // First try standard global variables
                        if (window.renderer && window.scene && window.camera) {
                            console.log('Found standard globals');
                            window.renderer.render(window.scene, window.camera);
                            rendererFound = true;
                        }
                        
                        // If not found, try to call animate
                        if (!rendererFound && typeof window.animate === 'function') {
                            console.log('Calling animate function');
                            window.animate();
                            rendererFound = true;
                        }
                        
                        return {
                            renderingSucceeded: rendererFound,
                            canvasCount: document.querySelectorAll('canvas').length,
                            hasGlobalRenderer: Boolean(window.renderer),
                            hasGlobalScene: Boolean(window.scene),
                            hasGlobalCamera: Boolean(window.camera)
                        };
                    } catch(e) {
                        return {error: e.message, stack: e.stack};
                    }
                }""")
                logger.info(f"Scene preparation: {scene_info}")
                
                # Wait for rendering to complete
                logger.info("Waiting for rendering to complete...")
                time.sleep(2)
                
                # Force a final render with multiple attempts
                logger.info("Forcing final render...")
                render_result = page.evaluate("""() => {
                    const results = {};
                    
                    // Approach 1: Standard render
                    try {
                        if (window.renderer && window.scene && window.camera) {
                            window.renderer.render(window.scene, window.camera);
                            results.standardRender = true;
                        } else {
                            results.standardRender = false;
                        }
                    } catch(e) {
                        results.standardRenderError = e.message;
                    }
                    
                    return results;
                }""")
                logger.info(f"Final render results: {render_result}")
                
                # Add a special WebGL rendering enforcer before taking the screenshot
                logger.info("Applying WebGL render enforcement for better page screenshots...")
                try:
                    # Force more aggressive rendering with direct WebGL commands
                    page.evaluate("""() => {
                        try {
                            // Try multiple rendering techniques
                            const canvases = document.querySelectorAll('canvas');
                            canvases.forEach(canvas => {
                                try {
                                    // Ensure canvas is visible and sized properly
                                    canvas.style.visibility = 'visible';
                                    canvas.style.opacity = '1';
                                    canvas.style.display = 'block';
                                    
                                    // Make sure it has size if needed
                                    if (canvas.width === 0 || canvas.height === 0) {
                                        canvas.width = Math.max(canvas.clientWidth, 800);
                                        canvas.height = Math.max(canvas.clientHeight, 600);
                                    }
                                    
                                    // Try to force a render
                                    if (window.renderer && window.renderer.render) {
                                        window.renderer.render(window.scene, window.camera);
                                    }
                                } catch (e) {
                                    console.error('Error preparing canvas:', e);
                                }
                            });
                            
                            // Add a slight delay to ensure the render completes
                            return new Promise(resolve => {
                                setTimeout(() => {
                                    // Force one final animation frame
                                    requestAnimationFrame(() => {
                                        requestAnimationFrame(() => {
                                            resolve('WebGL rendering enforced');
                                        });
                                    });
                                }, 500);
                            });
                        } catch (e) {
                            return `Error enforcing WebGL render: ${e.message}`;
                        }
                    }""")
                    
                    # Small wait after enforcing
                    time.sleep(0.5)
                except Exception as e:
                    logger.warning(f"Error in WebGL render enforcement: {e}")
                
                # Skip canvas screenshot and just take page screenshot directly
                logger.info("Taking page screenshot (skipping canvas screenshot attempt)...")
                try:
                    page.screenshot(path=self.screenshot_path)
                    logger.info(f"Page screenshot saved: {self.screenshot_path}")
                except Exception as e:
                    logger.error(f"Error taking page screenshot: {e}")
                
                # Close the browser
                logger.info("Closing Playwright browser...")
                context.close()
                browser.close()
                
                # Set screenshot complete flag
                self.screenshot_complete = True
                
        except Exception as e:
            logger.error(f"Error in Playwright session: {e}")
            self.screenshot_complete = True  # Mark as complete even on error

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
            
            # For Playwright with no-thread approach, browser is already closed
            logger.info("Playwright browser already closed (no thread mode)")
            self.running = False
            logger.info("Browser stopped")
            
        except Exception as e:
            logger.error(f"Error stopping browser: {e}")
            self.running = False
    
    def is_running(self):
        """Check if the browser is currently running"""
        return self.running


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
    finally:
        # Ensure browser is stopped
        if agent.browser_runner and agent.browser_runner.is_running():
            print("Stopping browser...")
            agent.browser_runner.stop_browser()
    
    print("Done!")


if __name__ == "__main__":
    main() 
else:
    # This ensures the agent is only registered once when imported
    __all__ = ["ThreeJSVisionAgent"] 