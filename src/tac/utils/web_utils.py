import logging
from typing import Dict, Optional, Tuple, List, Any
from playwright.sync_api import Page, sync_playwright, Browser, BrowserContext
import os
import sys
import platform
import subprocess
import tempfile
import uuid
import time
from tac.core.llm import Message

logger = logging.getLogger(__name__)

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

def ensure_playwright_installed():
    """Ensure Playwright browsers are installed."""
    if not PLAYWRIGHT_AVAILABLE:
        print("ERROR: Playwright is not installed.")
        print("Install with: pip install playwright")
        print("Then: playwright install chromium")
        return False
        
    try:
        print("Ensuring Playwright browsers are installed...")
        try:
            # Check if browsers are already installed
            with sync_playwright() as p:
                if p.chromium:
                    print("Playwright browsers already installed")
                    return True
                else:
                    raise Exception("Playwright browsers not installed")
            
        except Exception as e:
            print(f"Installing Playwright browsers: {e}")
            subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
            print("Playwright browsers installed successfully")
            return True
    except Exception as e:
        print(f"Warning: Could not verify or install Playwright browsers: {e}")
        print("If you encounter errors, run 'playwright install chromium' manually")
        return False

def get_browser_launch_options() -> Dict:
    """Get browser launch options with enhanced WebGL support"""
    return {
        "headless": True,
        "args": [
            "--use-gl=angle",
            "--use-angle=default",
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
    }

def get_browser_context_options() -> Dict:
    """Get browser context options"""
    return {
        "viewport": {"width": 1920, "height": 1080},
        "device_scale_factor": 1,
        "is_mobile": False,
        "has_touch": False,
        "locale": "en-US",
        "color_scheme": "dark",
        "forced_colors": "none",
        "reduced_motion": "no-preference"
    }

def verify_page_load(page: Page, timeout: int = 30000) -> Tuple[bool, List[str], Optional[Page]]:
    """
    Verify that a page loads correctly and is ready for interaction.
    
    Args:
        page: The Playwright Page object to verify
        timeout: Maximum time to wait for page load in milliseconds
        
    Returns:
        Tuple containing:
        - bool: True if page loaded successfully
        - List[str]: Any errors encountered
        - Optional[Page]: The page object if successful, None otherwise
    """
    collected_errors = []
    try:
        # Wait for the page to be ready
        page.wait_for_load_state("networkidle", timeout=timeout)
        
        # Check for JavaScript errors
        js_errors = page.evaluate("""() => {
            return window.errors || [];
        }""")
        if js_errors:
            collected_errors.extend(js_errors)
            
        # Check for failed requests
        failed_requests = page.evaluate("""() => {
            return window.failedRequests || [];
        }""")
        if failed_requests:
            collected_errors.extend(failed_requests)
            
        # Check if the page is responsive
        try:
            page.evaluate("""() => {
                return document.readyState === 'complete';
            }""")
        except Exception as e:
            collected_errors.append(f"Page not fully loaded: {str(e)}")
            
        return len(collected_errors) == 0, collected_errors, page
        
    except Exception as e:
        error_msg = f"Error verifying page load: {str(e)}"
        logger.error(error_msg)
        collected_errors.append(error_msg)
        return False, collected_errors, None

def take_page_screenshot(page: Page, output_dir: Optional[str] = None) -> str:
    """
    Take a screenshot of a webpage and return the file path.
    
    Args:
        page: Playwright Page object
        output_dir: Optional directory to save the screenshot in. If not provided,
                   a temporary directory will be used.
        
    Returns:
        str: Path to the saved screenshot file
        
    Raises:
        Exception: If screenshot fails to be taken
    """
    try:
        # Generate unique filename
        timestamp = int(time.time())
        unique_id = str(uuid.uuid4())[:8]
        
        # Create output directory if specified
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            screenshot_path = os.path.join(output_dir, f"screenshot_{timestamp}_{unique_id}.png")
        else:
            fd, screenshot_path = tempfile.mkstemp(prefix=f"screenshot_{timestamp}_{unique_id}_", suffix='.png')
            os.close(fd)
        
        logger.info(f"Taking screenshot, saving to: {screenshot_path}")
        
        # Take the screenshot
        page.screenshot(path=screenshot_path)
        
        # Verify the screenshot was created and has content
        if not os.path.exists(screenshot_path):
            raise Exception(f"Screenshot file was not created at {screenshot_path}")
            
        file_size = os.path.getsize(screenshot_path)
        if file_size == 0:
            raise Exception(f"Screenshot file is empty: {screenshot_path}")
            
        logger.info(f"Screenshot saved successfully: {screenshot_path} ({file_size} bytes)")
        return screenshot_path
        
    except Exception as e:
        error_msg = f"Failed to take screenshot: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)

def verify_page_load_with_browser(url: str, timeout: int = 30000) -> Tuple[bool, List[str], Optional[Page]]:
    """
    Launch a browser, navigate to a URL, and verify the page load.
    
    Args:
        url: The URL to navigate to
        timeout: Maximum time to wait for page load in milliseconds
        
    Returns:
        Tuple containing:
        - bool: True if page loaded successfully
        - List[str]: Any errors encountered
        - Optional[Page]: The page object if successful, None otherwise
    """
    playwright = None
    browser = None
    context = None
    page = None
    
    try:
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        # Navigate to the URL
        response = page.goto(url, wait_until="networkidle", timeout=timeout)
        if not response:
            return False, ["Failed to get response from page"], None
            
        if not response.ok:
            return False, [f"Page returned status code {response.status}"], None
            
        # Verify the page load
        return verify_page_load(page, timeout)
        
    except Exception as e:
        error_msg = f"Failed to load page: {str(e)}"
        logger.error(error_msg)
        return False, [error_msg], None
        
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

def take_threejs_screenshot(page: Page, output_dir: Optional[str] = None) -> str:
    """
    Take a screenshot of a Three.js scene after ensuring it's properly rendered.
    
    Args:
        page: Playwright Page object
        output_dir: Optional directory to save the screenshot in
        
    Returns:
        str: Path to the saved screenshot file
        
    Raises:
        Exception: If screenshot fails to be taken
    """
    try:
        # Check WebGL support
        webgl_support = page.evaluate("""() => {
            try {
                const canvas = document.createElement('canvas');
                return !!(canvas.getContext('webgl') || canvas.getContext('experimental-webgl'));
            } catch (e) {
                return false;
            }
        }""")
        
        if not webgl_support:
            raise Exception("WebGL is not supported in this browser")
            
        # Check Three.js status
        threejs_status = page.evaluate("""() => {
            if (typeof THREE === 'undefined') {
                return { success: false, error: 'THREE is not defined' };
            }
            
            // Check for common initialization functions
            const initFunctions = [
                'init',
                'animate',
                'render',
                'setupScene',
                'createScene',
                'setupThreeJS'
            ];
            
            const foundFunctions = initFunctions.filter(fn => typeof window[fn] === 'function');
            if (foundFunctions.length === 0) {
                return { success: false, error: 'No Three.js initialization functions found' };
            }
            
            // Try to find the renderer
            const renderer = window.renderer || document.querySelector('canvas')?.__threejs_renderer;
            if (!renderer) {
                return { success: false, error: 'No Three.js renderer found' };
            }
            
            return { success: true };
        }""")
        
        if not threejs_status.get('success'):
            raise Exception(f"Three.js scene not properly initialized: {threejs_status.get('error')}")
            
        # Prepare scene for rendering
        page.evaluate("""() => {
            // Try common initialization functions
            const initFunctions = [
                'init',
                'animate',
                'render',
                'setupScene',
                'createScene',
                'setupThreeJS'
            ];
            
            for (const fn of initFunctions) {
                if (typeof window[fn] === 'function') {
                    try {
                        window[fn]();
                    } catch (e) {
                        console.error(`Error in ${fn}:`, e);
                    }
                }
            }
            
            // Force a render if we have a renderer
            if (window.renderer) {
                window.renderer.render(window.scene, window.camera);
            }
            
            // Ensure canvas is visible and properly sized
            const canvas = document.querySelector('canvas');
            if (canvas) {
                canvas.style.display = 'block';
                canvas.style.width = '100%';
                canvas.style.height = '100%';
            }
        }""")
        
        # Take the screenshot
        return take_page_screenshot(page, output_dir)
        
    except Exception as e:
        error_msg = f"Failed to take Three.js screenshot: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)

def generate_unique_screenshot_path() -> str:
    """
    Generate a unique path for the screenshot to prevent reusing old screenshots.
    
    Returns:
        str: Path to the screenshot file
    """
    timestamp = int(time.time())
    unique_id = str(uuid.uuid4())[:8]
    fd, path = tempfile.mkstemp(prefix=f"screenshot_{timestamp}_{unique_id}_", suffix='.png')
    os.close(fd)
    logger.info(f"Generated unique screenshot path: {path}")
    return path

def analyze_screenshot(screenshot_path: str, prompt: str, llm_client: Any) -> str:
    """
    Analyze a screenshot using the vision model.
    
    Args:
        screenshot_path: Path to the screenshot file
        prompt: Prompt to use for analysis
        llm_client: The LLM client to use for analysis
        
    Returns:
        str: The analysis result
        
    Raises:
        Exception: If analysis fails
    """
    try:
        # Verify screenshot exists and has content
        if not os.path.exists(screenshot_path):
            raise Exception(f"Screenshot file not found: {screenshot_path}")
            
        file_size = os.path.getsize(screenshot_path)
        if file_size == 0:
            raise Exception(f"Screenshot file is empty: {screenshot_path}")
            
        # Create messages for the vision model
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
            
        # Use vision_chat_completion with the screenshot path
        response = llm_client.vision_chat_completion(messages, screenshot_path)
        if not response:
            raise Exception("No response from vision model")
            
        return response
        
    except Exception as e:
        error_msg = f"Failed to analyze screenshot: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)

def determine_vision_success(analysis_result: str, min_grade: str = "B") -> bool:
    """
    Determine if the vision analysis indicates success based on the grade.
    
    Args:
        analysis_result: The result of the vision analysis
        min_grade: Minimum passing grade (A, B, C, D, or F)
        
    Returns:
        bool: True if the grade meets or exceeds the minimum required grade
    """
    try:
        # Validate minimum grade
        if min_grade not in {"A", "B", "C", "D", "F"}:
            logger.warning(f"Invalid minimum grade: {min_grade}, defaulting to 'B'")
            min_grade = "B"
        
        # Define grade values (A=4, B=3, C=2, D=1, F=0)
        grade_values = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
        min_grade_value = grade_values[min_grade]
        
        # Extract grade from the analysis - check for both formats
        if "GRADE:" in analysis_result:
            grade_line = analysis_result.split("GRADE:")[1].split("\n")[0].strip()
            grade = grade_line[0].upper()  # Take first character as grade
            
            if grade not in grade_values:
                logger.error(f"Invalid grade found in analysis: {grade}")
                return False
            
            # Compare grade values
            return grade_values[grade] >= min_grade_value
        
        # Check for markdown format "## GRADE"
        elif "## GRADE" in analysis_result:
            # Split at "## GRADE" and take the part after it
            grade_section = analysis_result.split("## GRADE")[1].strip()
            # Extract just the letter grade, ignoring any additional text
            grade = None
            for char in grade_section:
                if char in "ABCDF":
                    grade = char
                    break
            
            if not grade:
                logger.error("No valid grade character found in the grade section")
                return False
                
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

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Test webpage loading and screenshot functionality')
    parser.add_argument('--html_file', required=True, help='Path to HTML file to test')
    parser.add_argument('--timeout', type=int, default=30000, help='Timeout in milliseconds (default: 30000)')
    parser.add_argument('--output_dir', help='Directory to save screenshot (optional)')
    
    args = parser.parse_args()
    
    # Convert file path to URL
    file_url = f"file://{os.path.abspath(args.html_file)}"
    
    playwright = None
    browser = None
    context = None
    page = None
    
    try:
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        # Navigate to the URL
        response = page.goto(file_url, wait_until="networkidle", timeout=args.timeout)
        if not response:
            print("Failed to get response from page")
            sys.exit(1)
            
        if not response.ok:
            print(f"Page returned status code {response.status}")
            sys.exit(1)
            
        # Verify the page load
        success, errors, page = verify_page_load(page, args.timeout)
        if not success:
            print("Failed to load page:")
            for error in errors:
                print(f"- {error}")
            sys.exit(1)
        
        # Take screenshot
        try:
            screenshot_path = take_page_screenshot(page, args.output_dir)
            print(f"Screenshot saved to: {screenshot_path}")
        except Exception as e:
            print(f"Failed to take screenshot: {e}")
            sys.exit(1)
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
        
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