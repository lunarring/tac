import logging
from typing import Dict, Optional, Tuple, List
from playwright.sync_api import Page, sync_playwright, Browser, BrowserContext
import os
import sys
import platform
import subprocess
import tempfile
import uuid
import time

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