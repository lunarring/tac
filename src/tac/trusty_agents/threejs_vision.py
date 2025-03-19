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

# Check if Playwright is installed
PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
    logger.info("Playwright is available for advanced WebGL screenshot support")
except ImportError:
    logger.warning("Playwright not found, will use Selenium for screenshots")
    logger.warning("For better WebGL support, install Playwright: pip install playwright")

# Check if Selenium is available
SELENIUM_AVAILABLE = False
try:
    import selenium
    from selenium import webdriver
    SELENIUM_AVAILABLE = True
    logger.info("Selenium is available for basic screenshot support")
except ImportError:
    logger.warning("Selenium not found. If Playwright is also unavailable, screenshots won't work")
    logger.warning("For basic support, install Selenium: pip install selenium webdriver-manager")

@trusty_agent(
    name="threejs_vision",
    description="Use this trusty agent to verify the visual output of web applications. Use it for anything visual with web content like html, threejs, or webgl.",
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
            timeout = config.general.vision_timeout or 15  # Default to 15 seconds
            screenshot_delay = config.general.vision_screenshot_delay or 3  # Default to 3 seconds
            
            # Check if headless mode is enabled in config, defaulting to True if not set
            headless = True  # Default to True for consistency with main()
            if hasattr(config.general, 'vision_headless'):
                headless = bool(getattr(config.general, 'vision_headless'))
            
            # Check if playwright should be used, defaulting to True if available and not explicitly disabled
            use_playwright = PLAYWRIGHT_AVAILABLE
            if hasattr(config.general, 'use_playwright'):
                use_playwright = bool(getattr(config.general, 'use_playwright'))
            
            if use_playwright and not PLAYWRIGHT_AVAILABLE:
                logger.warning("Playwright was requested but is not available. Falling back to Selenium.")
                use_playwright = False
                
                # Verify Selenium is available
                if not SELENIUM_AVAILABLE:
                    return False, "Neither Playwright nor Selenium are available. Cannot take screenshots.", "Browser not available"
            
            logger.info(f"Browser config: timeout={timeout}s, screenshot_delay={screenshot_delay}s, headless={headless}, use_playwright={use_playwright}")
            
            # Debug the HTML content if file size is small enough
            try:
                file_size = os.path.getsize(app_file_path)
                if file_size < 50000:  # Only log if file is under 50KB
                    with open(app_file_path, 'r') as f:
                        html_content = f.read()
                    logger.info(f"HTML content ({len(html_content)} bytes):\n{html_content[:500]}...")
                    
                    # Check if the HTML contains Three.js script tags
                    if "three.js" in html_content.lower() or "three.min.js" in html_content.lower():
                        logger.info("Found Three.js script tag in HTML content")
                    else:
                        logger.warning("No Three.js script tag found in HTML content")
                    
                    # Check for specific color references in the code
                    if "0xff0000" in html_content or "red" in html_content.lower():
                        logger.info("Found RED color references in the HTML content")
                    if "0x00ff00" in html_content or "green" in html_content.lower():
                        logger.info("Found GREEN color references in the HTML content")
                    if "0x0000ff" in html_content or "blue" in html_content.lower():
                        logger.info("Found BLUE color references in the HTML content")
                    
                    # Check for external JS files that might need time to load
                    import re
                    js_files = re.findall(r'<script.*?src=[\'"](.+?)[\'"]', html_content)
                    if js_files:
                        logger.info(f"Found external JS files: {js_files}")
                        # Increase delay for external files
                        if screenshot_delay < 3:
                            screenshot_delay = 3
                            logger.info(f"Increased screenshot delay to {screenshot_delay}s for external JS files")
            except Exception as e:
                logger.warning(f"Could not read HTML content: {e}")
                
            # Create browser runner with the current settings
            self.browser_runner = BrowserRunner(app_file_path, timeout=timeout, 
                                                screenshot_delay=screenshot_delay, 
                                                headless=headless)
            
            # Force Playwright usage if configured
            if use_playwright:
                self.browser_runner.use_playwright = True
                logger.info("Forcing use of Playwright for better WebGL support")
            
            logger.info(f"Starting browser with headless={headless}, use_playwright={self.browser_runner.use_playwright}...")
            self.browser_runner.start_browser()
            
            # If not using Playwright, need to wait for screenshot
            if not use_playwright:
                # Wait for the screenshot to be taken
                logger.info(f"Waiting for screenshot to be taken (may take several seconds)...")
                screenshot_wait_total = screenshot_delay + 5  # Give extra buffer time
                
                timer_start = time.time()
                while (time.time() - timer_start) < screenshot_wait_total:
                    if self.browser_runner.screenshot_complete:
                        logger.info(f"Screenshot completed in {time.time() - timer_start:.1f} seconds")
                        break
                    time.sleep(0.5)  # Check every half second
            
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
    def __init__(self, html_file_path, timeout=None, screenshot_delay=5, headless=False):
        """
        Initialize the BrowserRunner with the path to the HTML file.
        
        Args:
            html_file_path (str): Path to the HTML file to open
            timeout (int, optional): Timeout in seconds after which the browser will be closed.
                                    None means no timeout (run indefinitely until stopped manually).
            screenshot_delay (int, optional): Delay in seconds before taking a screenshot.
            headless (bool, optional): Whether to run the browser in headless mode.
        """
        self.html_file_path = html_file_path
        self.driver = None
        self.running = False
        self.timeout = timeout
        self.timeout_thread = None
        self.screenshot_delay = screenshot_delay
        self.screenshot_thread = None
        self.screenshot_path = None
        self.headless = bool(headless)  # Ensure it's a boolean
        self.screenshot_complete = False  # New flag to track screenshot completion
        self.threejs_status = None  # Store Three.js status
        self.use_playwright = PLAYWRIGHT_AVAILABLE  # Use Playwright if available
        self.playwright_browser = None
        self.playwright_page = None
        logger.info(f"BrowserRunner initialized with headless={self.headless}, use_playwright={self.use_playwright}")
        
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
            if self.use_playwright:
                self._start_playwright_no_thread()
            else:
                self._start_selenium()
            
            self.running = True
            
            # Start timeout thread if timeout is specified and not using Playwright
            if self.timeout is not None and not self.use_playwright:
                self.timeout_thread = threading.Thread(target=self._timeout_monitor)
                self.timeout_thread.daemon = True
                self.timeout_thread.start()
            
            # Start screenshot thread only for Selenium
            if not self.use_playwright:
                self.screenshot_thread = threading.Thread(target=self._take_screenshot_after_delay)
                self.screenshot_thread.daemon = True
                self.screenshot_thread.start()
            
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
                    "headless": self.headless,
                }
                
                # Add extreme WebGL support flags for headless mode
                if self.headless:
                    # These args are critical for WebGL in headless mode
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
                    
                    if platform.system() == 'Darwin':
                        # macOS specific optimizations
                        launch_options["args"].extend([
                            "--use-angle=metal",  # Use Metal on macOS
                            "--enable-features=Metal"
                        ])
                
                logger.info(f"Launching browser with enhanced WebGL options: {launch_options}")
                
                # Try with Chromium first (best WebGL support)
                browser = playwright.chromium.launch(**launch_options)
                
                # Create context with enhanced browser settings
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
                
                # Set additional permissions
                context.grant_permissions(['clipboard-read', 'clipboard-write'])
                
                page = context.new_page()
                
                # Add extra JavaScript helpers for debugging and WebGL support
                page.add_init_script("""
                    // Add WebGL debugging
                    window.webGLDebug = {
                        errors: [],
                        logging: true
                    };
                    
                    // Override the console.error to capture WebGL errors
                    const originalConsoleError = console.error;
                    console.error = function() {
                        if (window.webGLDebug && window.webGLDebug.logging) {
                            window.webGLDebug.errors.push(Array.from(arguments).join(' '));
                        }
                        originalConsoleError.apply(console, arguments);
                    };
                    
                    // Helper to create a working WebGL context if needed
                    window.createForcedWebGLContext = function(canvas) {
                        const contextNames = ['webgl2', 'webgl', 'experimental-webgl'];
                        let gl = null;
                        
                        for (const name of contextNames) {
                            try {
                                gl = canvas.getContext(name, {
                                    alpha: true,
                                    antialias: true,
                                    depth: true,
                                    failIfMajorPerformanceCaveat: false,
                                    powerPreference: 'high-performance',
                                    premultipliedAlpha: true,
                                    preserveDrawingBuffer: true,
                                    stencil: true
                                });
                                if (gl) {
                                    console.log('Created WebGL context with', name);
                                    break;
                                }
                            } catch (e) {
                                console.error('Error creating WebGL context with', name, e);
                            }
                        }
                        
                        return gl;
                    };
                """)

                # Read file content to check for external resources
                try:
                    with open(self.html_file_path, 'r') as f:
                        html_content = f.read()
                        
                    # Extract external JS files to ensure they're properly loaded
                    import re
                    js_files = re.findall(r'<script.*?src=[\'"](.+?)[\'"]', html_content)
                    logger.info(f"Detected external JS files: {js_files}")
                    
                    # Check if main.js is referenced and try to read its content
                    has_main_js = any('main.js' in js for js in js_files)
                    main_js_content = None
                    
                    if has_main_js:
                        # Get the path to main.js
                        html_dir = os.path.dirname(os.path.abspath(self.html_file_path))
                        main_js_path = None
                        
                        for js in js_files:
                            if 'main.js' in js and not js.startswith('http'):
                                main_js_path = os.path.join(html_dir, js)
                                break
                            
                        if main_js_path and os.path.exists(main_js_path):
                            logger.info(f"Reading main.js content from {main_js_path}")
                            with open(main_js_path, 'r') as f:
                                main_js_content = f.read()
                                logger.info(f"main.js content preview: {main_js_content[:200]}...")
                
                except Exception as e:
                    logger.warning(f"Could not analyze HTML content: {e}")
                
                # Set up extra event listeners for better debugging
                page.on("console", lambda msg: logger.debug(f"CONSOLE {msg.type}: {msg.text}"))
                page.on("pageerror", lambda err: logger.error(f"PAGE ERROR: {err}"))
                
                # Navigate to page and wait for load
                logger.info(f"Navigating to: {file_url}")
                resp = page.goto(file_url, wait_until="networkidle", timeout=30000)
                logger.info(f"Page loaded with status: {resp.status}")
                
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
                
                # Try to manually execute main.js content if detected
                if main_js_content and 'hasThree' in threejs_status and threejs_status['hasThree'] and not threejs_status.get('hasRenderer'):
                    logger.info("Injecting and executing main.js content directly")
                    try:
                        # Inject and execute the main.js content directly
                        page.evaluate(f"""() => {{ 
                            try {{
                                // Execute the main.js content directly
                                {main_js_content}
                                return "Executed main.js content directly";
                            }} catch(e) {{
                                return `Error executing main.js content: ${{e.message}}`;
                            }}
                        }}""")
                    except Exception as e:
                        logger.error(f"Error injecting main.js content: {e}")
                
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

    def _start_selenium(self):
        """Start the browser with Selenium"""
        # Existing Selenium implementation
        # ... [existing Selenium code from start_browser] ...
        # Setup Chrome options
        chrome_options = Options()
        
        # Handle headless mode
        if self.headless:
            # Check if we're on macOS - headless WebGL support requires special handling
            is_macos = platform.system() == 'Darwin'
            
            if is_macos:
                logger.warning("Using specialized WebGL headless mode for macOS")
            
            logger.info("Running in headless mode with enhanced WebGL support")
            
            # Setup optimal headless WebGL mode
            chrome_options.add_argument("--headless=new")  # Use new headless mode
            
            # Essential flags for headless WebGL
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--hide-scrollbars")
            chrome_options.add_argument("--use-gl=egl")  # Use EGL for better headless WebGL support
            chrome_options.add_argument("--ignore-gpu-blocklist")
            chrome_options.add_argument("--enable-gpu-rasterization")
            chrome_options.add_argument("--enable-webgl")
            chrome_options.add_argument("--enable-accelerated-2d-canvas")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")  # Overcome limited resource issues
            
            # Additional flag for macOS for better performance
            if is_macos:
                chrome_options.add_argument("--use-angle=metal")  # Use Metal backend on macOS
            
            # Setup WebGL and GPU preferences
            prefs = {
                "hardware_acceleration_mode.enabled": True,
                "webkit.webprefs.enable_webgl": True,
                "webgl.disabled": False,
                "dom.webgpu.enabled": True,  # Enable WebGPU as well
                "browser.enable_automatic_webgl_renderer_selection": False
            }
            chrome_options.add_experimental_option("prefs", prefs)
        else:
            logger.info("Running in visible mode (not headless)")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
        
        # Common options
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-web-security")  # Help with loading local resources
        chrome_options.add_argument("--allow-file-access-from-files")  # Help with loading local resources
        
        # Print all Chrome options for debugging
        logger.info("Chrome options:")
        for arg in chrome_options.arguments:
            logger.info(f"  {arg}")
            
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
        self.driver.implicitly_wait(5)  # Increased wait time
        
        # Force the browser to be active
        self.driver.execute_script("window.focus();")
        
        # Print page title for debugging
        logger.info(f"Page title: {self.driver.title}")
        
        # Wait for Three.js to initialize
        self._wait_for_threejs()

    def _take_screenshot_after_delay(self):
        """Take a screenshot after the specified delay using the most appropriate method"""
        try:
            # Wait for specified delay
            logger.info(f"Waiting {self.screenshot_delay} seconds before taking screenshot...")
            time.sleep(self.screenshot_delay)
            
            if not self.running:
                logger.info("Browser is no longer running, cannot take screenshot")
                self.screenshot_complete = True
                return
            
            # Create a temporary file for the screenshot
            self.screenshot_path = self._generate_unique_screenshot_path()
            
            # Wait for any animations or resources to load
            logger.info("Taking screenshot of Three.js application")
            
            # Take screenshot with the appropriate method
            success = False
            
            if self.use_playwright and self.playwright_page:
                try:
                    # Use Playwright for screenshot - IMPORTANT: Don't use separate thread operations here
                    logger.info("Taking screenshot with Playwright")
                    
                    # Force rendering using synchronous calls (avoid wait_for_timeout which uses async)
                    try:
                        # Force rendering one more time
                        self.playwright_page.evaluate("""() => {
                            try {
                                // Force WebGL rendering if possible
                                if (window.renderer && window.renderer.render) {
                                    window.renderer.render(window.scene || new THREE.Scene(), window.camera || new THREE.PerspectiveCamera());
                                }
                                
                                // Try to call animate function if it exists
                                if (typeof window.animate === 'function') {
                                    window.animate();
                                }
                                
                                // Force a final render call
                                if (window.requestAnimationFrame) {
                                    window.requestAnimationFrame(() => {});
                                }
                                return true;
                            } catch(e) {
                                return false;
                            }
                        }""")
                        
                        # Short sleep instead of async wait_for_timeout
                        time.sleep(0.5)
                        
                        # Take the screenshot - this must happen in the same thread
                        self.playwright_page.screenshot(path=self.screenshot_path)
                        success = os.path.exists(self.screenshot_path) and os.path.getsize(self.screenshot_path) > 0
                        logger.info(f"Playwright screenshot taken: {success}")
                    except Exception as render_error:
                        logger.error(f"Error during Playwright rendering: {render_error}")
                except Exception as e:
                    logger.error(f"Playwright screenshot failed: {e}")
                    # If Playwright fails, fall back to Selenium if available
                    if self.driver:
                        logger.info("Falling back to Selenium for screenshot")
                        try:
                            success = self.driver.save_screenshot(self.screenshot_path)
                            logger.info(f"Fallback screenshot taken: {success}")
                        except Exception as selenium_error:
                            logger.error(f"Selenium fallback also failed: {selenium_error}")
            elif self.driver:
                # Use Selenium for screenshot
                # Prepare the scene for rendering
                self._prepare_scene_for_rendering()
                
                # Pre-screenshot delay to ensure rendering is complete
                time.sleep(1.0)
                
                # Force WebGL rendering before taking screenshot (super important)
                self._force_webgl_rendering()
                
                try:
                    if self.headless:
                        # Use CDP screenshot if available (with GPU surface)
                        logger.info("Taking WebGL-optimized CDP screenshot in headless mode")
                        
                        # Use CDP screenshot method
                        success = self._take_cdp_screenshot(from_surface=True)
                        
                        # Fall back to standard screenshot if CDP fails
                        if not success or os.path.getsize(self.screenshot_path) < 10000:
                            logger.info("CDP screenshot may have failed, using standard screenshot")
                            success = self.driver.save_screenshot(self.screenshot_path)
                    else:
                        # For visible mode, just use standard screenshot
                        logger.info("Taking standard screenshot")
                        success = self.driver.save_screenshot(self.screenshot_path)
                    
                    logger.info(f"Screenshot taken: {success}")
                except Exception as e:
                    logger.error(f"Error during screenshot capture: {e}")
            else:
                logger.error("No screenshot method available - both Playwright and Selenium unavailable")
            
            # Verify the screenshot
            if os.path.exists(self.screenshot_path) and os.path.getsize(self.screenshot_path) > 0:
                logger.info(f"Screenshot saved to {self.screenshot_path} ({os.path.getsize(self.screenshot_path)} bytes)")
                self._analyze_screenshot()
            else:
                logger.error(f"Screenshot file is empty or missing: {self.screenshot_path}")
                
            # Mark screenshot as complete
            self.screenshot_complete = True
                
        except Exception as e:
            logger.error(f"Error taking screenshot: {e}")
            self.screenshot_complete = True  # Mark as complete even if failed
    
    def _force_webgl_rendering(self):
        """Force WebGL to render content before taking screenshot - critical for headless mode"""
        try:
            force_script = """
            try {
                // Ensure WebGL is enabled and working
                const testCanvas = document.createElement('canvas');
                const gl = testCanvas.getContext('webgl') || testCanvas.getContext('experimental-webgl');
                const webglSupported = !!gl;
                
                // Try to force Three.js rendering on all possible canvases
                const canvases = document.querySelectorAll('canvas');
                
                // Get any renderer or THREE objects from the global scope
                let renderers = [];
                for (let key in window) {
                    try {
                        if (window[key] && typeof window[key] === 'object' && typeof window[key].render === 'function') {
                            renderers.push(window[key]);
                        }
                    } catch (e) {}
                }
                
                // For each canvas, try to force a render
                const renderResults = [];
                canvases.forEach((canvas, i) => {
                    // Force any animation frame callbacks to execute
                    if (window.requestAnimationFrame) {
                        const rafPromise = new Promise(resolve => {
                            window.requestAnimationFrame(() => {
                                window.requestAnimationFrame(() => {
                                    resolve();
                                });
                            });
                        });
                    }
                    
                    // Try to create a renderer for this canvas if we found one
                    if (renderers.length > 0) {
                        renderers.forEach(renderer => {
                            try {
                                if (renderer.domElement === canvas) {
                                    renderer.render(renderer.scene || window.scene, renderer.camera || window.camera);
                                    renderResults.push({canvas: i, rendered: true});
                                }
                            } catch (e) {}
                        });
                    }
                    
                    // If THREE is available, try to create a new renderer
                    if (window.THREE && !canvas.processed) {
                        try {
                            logger.info("Not creating a temporary scene for this canvas - removed fallback");
                            renderResults.push({canvas: i, notProcessed: true, reason: "Fallback disabled"});
                        } catch (e) {
                            renderResults.push({canvas: i, error: e.toString()});
                        }
                    }
                });
                
                // Try to call any animate functions
                if (typeof window.animate === 'function') {
                    try {
                        window.animate();
                    } catch (e) {}
                }
                
                // If found an existing animation render function, call it
                if (typeof window.render === 'function') {
                    try {
                        window.render();
                    } catch (e) {}
                }
                
                return {
                    webglSupported: webglSupported,
                    canvasCount: canvases.length,
                    renderResults: renderResults
                };
            } catch (e) {
                return {error: e.toString()};
            }
            """
            result = self.driver.execute_script(force_script)
            logger.info(f"WebGL rendering preparation: {result}")
            return result
        except Exception as e:
            logger.error(f"Error forcing WebGL rendering: {e}")
            return None
    
    def _take_cdp_screenshot(self, from_surface=True):
        """
        Use Chrome DevTools Protocol for capturing WebGL content in headless mode
        
        Args:
            from_surface: Whether to capture from GPU surface (needed for WebGL)
        """
        try:
            # Try the most reliable CDP method - execute_cdp_cmd
            logger.info(f"Taking CDP screenshot with fromSurface={from_surface}")
            screenshot_data = self.driver.execute_cdp_cmd('Page.captureScreenshot', {
                'format': 'png', 
                'fromSurface': from_surface,  # This captures from the GPU surface, which includes WebGL
                'captureBeyondViewport': True,  # This captures the entire page
                'quality': 100  # Maximum quality
            })
            
            # Check for screenshot data
            if 'data' in screenshot_data:
                import base64
                image_data = base64.b64decode(screenshot_data['data'])
                with open(self.screenshot_path, "wb") as f:
                    f.write(image_data)
                logger.info(f"CDP screenshot saved ({len(image_data)} bytes)")
                return True
            else:
                logger.error("No data in CDP screenshot response")
                return False
                
        except Exception as e:
            logger.error(f"CDP screenshot failed: {e}")
            return False
    
    def _prepare_scene_for_rendering(self):
        """Prepare the Three.js scene for rendering by executing various forcing scripts"""
        logger.info("Preparing Three.js scene for rendering")
        try:
            # Execute JavaScript to ensure WebGL renderer is initialized and rendering
            init_script = """
            try {
                // Resize canvas if needed
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
                
                // Try to access scene and renderer objects by traversing DOM objects
                if (!rendererFound) {
                    for (let key in window) {
                        try {
                            const obj = window[key];
                            // Check if it's a THREE.js scene
                            if (obj && typeof obj === 'object' && obj.type === 'Scene') {
                                console.log('Found Scene in', key);
                                window.scene = obj;
                            }
                            // Check if it's a THREE.js renderer
                            if (obj && typeof obj === 'object' && typeof obj.render === 'function') {
                                console.log('Found renderer in', key);
                                window.renderer = obj;
                            }
                            // Check if it's a THREE.js camera
                            if (obj && typeof obj === 'object' && obj.type === 'Camera' || obj.type === 'PerspectiveCamera') {
                                console.log('Found camera in', key);
                                window.camera = obj;
                            }
                        } catch (e) {}
                    }
                    
                    // Try rendering with discovered objects
                    if (window.renderer && window.scene && window.camera) {
                        console.log('Rendering with discovered objects');
                        window.renderer.render(window.scene, window.camera);
                        rendererFound = true;
                    }
                }
                
                return {
                    renderingSucceeded: rendererFound,
                    canvasCount: canvases.length,
                    hasGlobalRenderer: Boolean(window.renderer),
                    hasGlobalScene: Boolean(window.scene),
                    hasGlobalCamera: Boolean(window.camera)
                };
            } catch(e) {
                return {error: e.message, stack: e.stack};
            }
            """
            init_result = self.driver.execute_script(init_script)
            logger.info(f"Rendering initialization: {init_result}")
            
            # Update Three.js status with rendering information
            if isinstance(init_result, dict) and isinstance(self.threejs_status, dict):
                self.threejs_status.update(init_result)
            else:
                self.threejs_status = init_result
            
            # Give time for rendering to complete
            time.sleep(1.0)
            
        except Exception as e:
            logger.warning(f"Error preparing scene: {e}")
    
    def _analyze_screenshot(self):
        """Analyze the captured screenshot to check if it's valid"""
        try:
            if not os.path.exists(self.screenshot_path):
                logger.warning("Cannot analyze - screenshot file doesn't exist")
                return
                
            file_size = os.path.getsize(self.screenshot_path)
            if file_size == 0:
                logger.warning("Cannot analyze - screenshot file is empty")
                return
                
            # Use PIL to check the image
            from PIL import Image, ImageStat
            with Image.open(self.screenshot_path) as img:
                width, height = img.size
                logger.info(f"Screenshot dimensions: {width}x{height}")
                
                # Check if image is blank (all one color)
                stat = ImageStat.Stat(img)
                if len(set(int(x) for x in stat.mean)) == 1:
                    logger.warning("Screenshot appears to be blank (single color)")
                
                # Sample pixels to see if there's variation
                pixels = []
                for x in range(0, width, width//10):
                    for y in range(0, height, height//10):
                        try:
                            pixels.append(img.getpixel((x, y)))
                        except:
                            pass
                
                unique_pixels = len(set(pixels))
                logger.info(f"Unique colors in screenshot sample: {unique_pixels}")
                if unique_pixels < 5:
                    logger.warning("Screenshot has very few colors, may not contain Three.js content")
                
        except Exception as e:
            logger.warning(f"Error analyzing screenshot: {e}")
    
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
            if self.use_playwright:
                logger.info("Playwright browser already closed (no thread mode)")
                self.running = False
                return
            
            # Stop Selenium if it was used
            if self.driver:
                try:
                    self.driver.quit()
                    logger.info("Selenium browser stopped")
                except Exception as e:
                    logger.error(f"Error stopping Selenium browser: {e}")
                finally:
                    self.driver = None
            
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
    parser.add_argument('--headless', action='store_true', help='Run browser in headless mode with advanced WebGL support')
    parser.add_argument('--no-headless', dest='headless', action='store_false', help='Run browser in visible mode (use this if you want to see the browser window)')
    parser.add_argument('--use-playwright', action='store_true', help='Use Playwright instead of Selenium (better WebGL support)')
    parser.add_argument('--use-selenium', dest='use_playwright', action='store_false', help='Force the use of Selenium instead of Playwright')
    
    # Set headless and playwright to true by default
    parser.set_defaults(headless=True, use_playwright=True)
    
    args = parser.parse_args()
    
    # Check if Playwright is requested but not available
    if args.use_playwright and not PLAYWRIGHT_AVAILABLE:
        print("ERROR: Playwright was requested but is not installed.")
        print("Install with: pip install playwright")
        print("Then: playwright install chromium")
        
        if SELENIUM_AVAILABLE:
            print("Falling back to Selenium...")
            args.use_playwright = False
        else:
            return
    
    # Ensure Playwright browsers are installed if needed
    if args.use_playwright and PLAYWRIGHT_AVAILABLE:
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
    
    # Create a dummy ProtoBlock
    class DummyProtoBlock:
        def __init__(self, html_file):
            self.block_id = "test"
            self.write_files = [html_file]
            self.context_files = []
            self._trusty_agent_prompts = {
                "threejs_vision": " Review the updated Three.js scene ensuring that there are now two cubes rendered."
            }
            
        @property
        def trusty_agent_prompts(self):
            return self._trusty_agent_prompts
    
    # Set print messages based on settings
    headless_mode = bool(args.headless)
    
    # Print configuration messages
    print(f"Testing Three.js vision agent with {html_file}")
    prompt_text = protoblock.trusty_agent_prompts.get('threejs_vision', '').strip()
    if prompt_text:
        print(f"Checking: {prompt_text[:70]}...")
    else:
        print(f"Checking Three.js scene rendering...")
    print(f"Timeout: {args.timeout} seconds, Screenshot delay: {args.delay} seconds")
    print(f"Mode: {'Headless' if headless_mode else 'Visible'}")
    print(f"Engine: {'Playwright' if args.use_playwright else 'Selenium'}")
    
    if args.use_playwright and headless_mode and platform.system() == 'Darwin':
        print("NOTE: Using specialized WebGL settings for macOS headless mode")
    
    # Initialize the agent
    agent = ThreeJSVisionAgent()
    
    # Set the config values before agent initialization
    config.general.vision_timeout = args.timeout
    config.general.vision_screenshot_delay = args.delay
    config.general.vision_headless = headless_mode
    config.general.use_playwright = args.use_playwright
    
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