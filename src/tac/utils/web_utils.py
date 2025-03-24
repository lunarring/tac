import logging
from typing import Dict, Optional, Tuple, List
from playwright.sync_api import Page, sync_playwright, Browser, BrowserContext
import os
import sys
import platform
import subprocess

logger = logging.getLogger(__name__)

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

def verify_page_load(url: str, timeout: int = 30000) -> Tuple[bool, List[str], Optional[Page]]:
    """
    Verify if a webpage has loaded correctly by checking for JavaScript errors,
    resource loading failures, and page status.
    
    Args:
        url: URL or file path to load
        timeout: Timeout in milliseconds (default: 30000)
        
    Returns:
        tuple containing:
        - bool: True if page loaded successfully, False otherwise
        - list[str]: List of collected errors if any
        - Optional[Page]: The page object if successful, None otherwise
    """
    collected_errors = []
    page = None
    browser = None
    context = None
    playwright = None

    try:
        playwright = sync_playwright().start()
        # Launch browser with enhanced WebGL support
        browser = playwright.chromium.launch(**get_browser_launch_options())
        context = browser.new_context(**get_browser_context_options())
        page = context.new_page()

        def handle_console(msg):
            if msg.type == "error":
                error_msg = f"Console error: {msg.text}"
                logger.error(error_msg)
                if any(x in msg.text.lower() for x in [
                    "is not defined", "undefined", "cannot read properties",
                    "syntax error", "reference error", "type error",
                    "failed to load resource", "refused to execute script",
                    "mime type"
                ]):
                    collected_errors.append(error_msg)
                    return False
            return True

        def handle_page_error(err):
            error_msg = f"Page error: {err}"
            logger.error(error_msg)
            if any(x in str(err).lower() for x in [
                "is not defined", "undefined", "cannot read properties",
                "syntax error", "reference error", "type error"
            ]):
                collected_errors.append(error_msg)
                return False
            return True

        def handle_request_failed(request):
            try:
                error_text = request.failure.get('errorText', 'Unknown error')
                error_msg = f"Request failed: {request.url} - {error_text}"
                logger.error(error_msg)
                if request.resource_type in ["script", "stylesheet"]:
                    collected_errors.append(error_msg)
                    return False
            except Exception as e:
                error_msg = f"Error handling request failure: {str(e)}"
                logger.error(error_msg)
                collected_errors.append(error_msg)
                return False
            return True

        # Set up error handlers
        page.on("console", handle_console)
        page.on("pageerror", handle_page_error)
        page.on("requestfailed", handle_request_failed)

        # Navigate to the page
        logger.info(f"Navigating to: {url}")
        resp = page.goto(url, wait_until="networkidle", timeout=timeout)
        
        if not resp:
            collected_errors.append("Page navigation failed - no response received")
            return False, collected_errors, None
            
        if resp.status >= 400:
            collected_errors.append(f"Page navigation failed with status {resp.status}")
            return False, collected_errors, None

        # Check for JavaScript errors
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
            for error in js_errors:
                error_msg = f"JavaScript error: {error.get('message')}"
                if error.get('url'):
                    error_msg += f" at {error.get('url')}:{error.get('line')}:{error.get('column')}"
                if error.get('stack'):
                    error_msg += f"\nStack trace:\n{error.get('stack')}"
                collected_errors.append(error_msg)

        return len(collected_errors) == 0, collected_errors, page

    except Exception as e:
        error_msg = f"Error during page verification: {str(e)}"
        logger.error(error_msg)
        collected_errors.append(error_msg)
        return False, collected_errors, None

    finally:
        # Clean up resources in reverse order of creation
        if context:
            try:
                context.close()
            except Exception as e:
                logger.warning(f"Error closing context: {e}")
        if browser:
            try:
                browser.close()
            except Exception as e:
                logger.warning(f"Error closing browser: {e}")
        if playwright:
            try:
                playwright.stop()
            except Exception as e:
                logger.warning(f"Error stopping playwright: {e}")

if __name__ == "__main__":
    """Example usage of verify_page_load"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test webpage loading verification')
    parser.add_argument('--html_file', default='index.html', 
                       help='Path to the HTML file to test')
    parser.add_argument('--timeout', type=int, default=10, 
                       help='Timeout in seconds (default: 10)')
    
    args = parser.parse_args()
    
    # Check if Playwright is available
    try:
        from playwright.sync_api import sync_playwright
        print("Playwright is available")
    except ImportError:
        print("ERROR: Playwright is not installed.")
        print("Install with: pip install playwright")
        print("Then: playwright install chromium")
        sys.exit(1)
    
    # Ensure Playwright browsers are installed
    try:
        print("Ensuring Playwright browsers are installed...")
        try:
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
        sys.exit(1)
    
    # Print configuration messages
    print(f"Testing webpage loading verification with {html_file}")
    print(f"Timeout: {args.timeout} seconds")
    print("Mode: Headless")
    print("Engine: Playwright")
    
    if platform.system() == 'Darwin':
        print("NOTE: Using specialized WebGL settings for macOS headless mode")
    
    # Use the verify_page_load function
    file_url = f"file://{os.path.abspath(html_file)}"
    success, errors, page = verify_page_load(file_url, timeout=args.timeout * 1000)
    
    if success:
        print("\nSuccess! Page loaded correctly with no errors.")
    else:
        print("\nError: Page loaded with issues:")
        for error in errors:
            print(f"- {error}")
        sys.exit(1)
    
    print("\nDone!") 