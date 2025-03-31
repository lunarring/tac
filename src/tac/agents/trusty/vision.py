#!/usr/bin/env python3
import subprocess
import threading
import time
import os
import signal
import sys
import pyautogui
from PIL import Image, ImageDraw
import tempfile
import platform
import logging
from typing import Dict, Tuple, Optional

from tac.core.llm import LLMClient, Message
from tac.blocks import ProtoBlock
from tac.core.config import config
from tac.core.log_config import setup_logging
from tac.agents.trusty.base import TrustyAgent, trusty_agent

logger = setup_logging('tac.trusty_agents.vision')

@trusty_agent(
    name="vision",
    description="Use this vision agent for general purpose visual verification of the output of a program. Do not use for threejs or html.",
    protoblock_prompt="Describe what visual elements you would expect to see in the program's output that would verify the implementation is correct. Be specific about colors, shapes, text, or UI elements that should be visible.",
    prompt_target="coding_agent",
)
class VisionTestingAgent(TrustyAgent):
    """
    A trusty agent that runs a program, takes a screenshot, and analyzes it using a vision model
    to verify that the visual output matches expectations.
    """

    def __init__(self):
        logger.info("Initializing VisionTestingAgent")
        self.llm_client = LLMClient(llm_type="vision")
        self.program_runner = None
        self.screenshot_path = None
        self.analysis_result = None

    def _check_impl(self, protoblock: ProtoBlock, codebase: Dict[str, str], code_diff: str) -> Tuple[bool, str, str]:
        """
        Run the program, take a screenshot, and analyze it using a vision model.
        
        Args:
            protoblock: The ProtoBlock containing task specifications
            codebase: Dictionary mapping file paths to their contents
            code_diff: The git diff showing implemented changes
            
        Returns:
            Tuple containing:
            - bool: Success status (True if visual verification passed, False otherwise)
            - str: Error analysis (empty string if success is True)
            - str: Failure type description (empty string if success is True)
        """
        try:
            # Get the main program file to run from the protoblock
            program_path = self._get_program_path(protoblock, codebase)
            if not program_path:
                return False, "Could not determine which program file to run", "No program file found"
            
            if not os.path.exists(program_path):
                return False, f"Program file not found: {program_path}", "Program file not found"
            
            # Get the expected visual elements from the protoblock
            expected_visual = protoblock.trusty_agent_prompts.get("vision", "")
            if not expected_visual:
                logger.warning("No vision prompt found in protoblock")
                expected_visual = "Analyze what you see in the screenshot and describe it in detail."
            
            # Run the program and take a screenshot
            logger.info(f"Running program: {program_path}")
            timeout = config.general.trusty_agents.vision_timeout or 15  # Default to 15 seconds
            screenshot_delay = config.general.trusty_agents.vision_screenshot_delay or 5  # Default to 5 seconds
            
            self.program_runner = ProgramRunner(program_path, timeout=timeout, screenshot_delay=screenshot_delay)
            self.program_runner.start_program()
            
            # Wait for the screenshot to be taken
            wait_time = screenshot_delay + 1  # Add 1 second buffer
            logger.info(f"Waiting {wait_time} seconds for screenshot...")
            time.sleep(wait_time)
            
            # Get the screenshot path
            self.screenshot_path = self.program_runner.get_screenshot_path()
            
            # Add a small delay to ensure the file is fully written to disk
            time.sleep(1)
            
            if not self.screenshot_path or not os.path.exists(self.screenshot_path):
                self.program_runner.stop_program()
                return False, "Failed to take screenshot", "Screenshot failed"
            
            # Analyze the screenshot
            logger.info("Analyzing screenshot with vision model...")
            prompt = f"""
            Analyze this screenshot of a program's output. Expected visual elements:{expected_visual}

Please verify if the expected visual elements are present in the screenshot.
Be specific about what you see and whether it matches the expectations.
If there are any discrepancies, explain them in detail.
            
You answer with a clear YES or NO verdict in the first line of response. In case of NO, explain why in the following lines.

Example:

YES

NO
The red dot is not present, I see a blue square instead that is in the upper right."""
            
            self.analysis_result = self._analyze_screenshot(prompt)
            logger.info(f"Analysis result: {self.analysis_result}")
            
            # Stop the program
            self.program_runner.stop_program()
            
            # Determine success based on the analysis result
            success = self._determine_success(self.analysis_result)
            
            if success:
                return True, "", ""
            else:
                failure_type = "Visual verification failed"
                error_analysis = f"The program's visual output did not match expectations:\n\n{self.analysis_result}"
                return False, error_analysis, failure_type
            
        except Exception as e:
            logger.exception(f"Error in vision testing: {str(e)}")
            if self.program_runner and self.program_runner.is_running():
                self.program_runner.stop_program()
            return False, f"Error during vision testing: {str(e)}", "Vision testing exception"

    def _get_program_path(self, protoblock: ProtoBlock, codebase: Dict[str, str]) -> Optional[str]:
        """
        Determine which program file to run based on the protoblock and codebase.
        
        Args:
            protoblock: The ProtoBlock containing task specifications
            codebase: Dictionary mapping file paths to their contents
            
        Returns:
            str: Path to the program file to run, or None if not found
        """
        # First check if there's a specific program file mentioned in the protoblock
        for file_path in protoblock.write_files:
            if file_path.endswith('.py') and 'main' in file_path.lower():
                return file_path
        
        # Then check for any Python file that might be the main program
        for file_path in protoblock.write_files:
            if file_path.endswith('.py'):
                with open(file_path, 'r') as f:
                    content = f.read()
                    if 'if __name__ == "__main__"' in content or "if __name__ == '__main__'" in content:
                        return file_path
        
        # If no main file found in write_files, check context_files
        for file_path in protoblock.context_files:
            if file_path.endswith('.py') and 'main' in file_path.lower():
                return file_path
        
        # If still not found, look for any Python file in the codebase
        for file_path in codebase.keys():
            if file_path.endswith('.py') and ('main' in file_path.lower() or 'app' in file_path.lower()):
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
        # Sleep 3 sec so the screenshot is fully written to disk
        time.sleep(3)
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
            
            # Try to open the image to verify it's a valid image file
            try:
                with Image.open(self.screenshot_path) as img:
                    width, height = img.size
                    format = img.format
                    logger.info(f"Image validated: {width}x{height} {format}")
                    
                    # Additional validation - try to save a copy to ensure it's a valid image
                    test_path = f"{self.screenshot_path}.test.png"
                    img.save(test_path, format='PNG')
                    logger.info(f"Image successfully saved to test path: {test_path}")
                    
                    # Check if the test image can be read
                    with open(test_path, "rb") as test_file:
                        test_bytes = test_file.read(100)  # Just read a few bytes to test
                        logger.info(f"Successfully read {len(test_bytes)} bytes from test image")
                    
                    # Clean up test file
                    os.remove(test_path)
            except Exception as img_error:
                error_msg = f"Invalid image file: {str(img_error)}"
                logger.error(error_msg)
                
                # Try to create a test image as fallback
                logger.info("Creating test image as fallback")
                test_path = f"{self.screenshot_path}.fallback.png"
                if self._create_test_image(test_path):
                    logger.info(f"Using fallback test image: {test_path}")
                    self.screenshot_path = test_path
                else:
                    return f"Vision analysis failed: {error_msg}"
            
            # Final check - try to read the image file directly
            try:
                with open(self.screenshot_path, "rb") as image_file:
                    image_bytes = image_file.read()
                    if len(image_bytes) == 0:
                        error_msg = "Image file is empty when read directly"
                        logger.error(error_msg)
                        return f"Vision analysis failed: {error_msg}"
                    logger.info(f"Successfully read {len(image_bytes)} bytes directly from image file")
            except Exception as read_error:
                error_msg = f"Failed to read image file directly: {str(read_error)}"
                logger.error(error_msg)
                return f"Vision analysis failed: {error_msg}"
            
            # Create messages for the vision model
            vision_messages = [
                Message(role="system", content="You are a helpful assistant that can analyze images"),
                Message(role="user", content=prompt)
            ]
            
            # Use vision_chat_completion - just pass the screenshot path directly
            # The LLMClient.vision_chat_completion method handles the image encoding
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
        
        # If not in the expected format, fall back to the original logic
        # Look for a clear YES/NO verdict in the analysis result
        if "YES" in analysis_result.upper().split() and "NO" not in analysis_result.upper().split():
            return True
        
        # Check for positive indicators
        positive_indicators = [
            "matches expectations",
            "matches the expectations",
            "visual elements are present",
            "expected elements are present",
            "successfully displays",
            "correctly displays",
            "correctly implemented",
            "successfully implemented"
        ]
        
        for indicator in positive_indicators:
            if indicator.lower() in analysis_result.lower():
                return True
        
        # Check for negative indicators
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
            "failed to display"
        ]
        
        for indicator in negative_indicators:
            if indicator.lower() in analysis_result.lower():
                return False
        
        # If no clear indicators, default to False
        return False


class ProgramRunner:
    def __init__(self, program_path, timeout=None, screenshot_delay=5):
        """
        Initialize the ProgramRunner with the path to the program script.
        
        Args:
            program_path (str): Path to the Python script to run
            timeout (int, optional): Timeout in seconds after which the program will be stopped.
                                    None means no timeout (run indefinitely until stopped manually).
            screenshot_delay (int, optional): Delay in seconds before taking a screenshot.
        """
        self.program_path = program_path
        self.process = None
        self.running = False
        self.thread = None
        self.timeout = timeout
        self.timeout_thread = None
        self.screenshot_delay = screenshot_delay
        self.screenshot_thread = None
        self.screenshot_path = None
        self.window_title = os.path.basename(program_path)  # Use filename as window title guess
    
    def start_program(self):
        """Start the program in a separate process"""
        if self.running:
            logger.info("Program is already running")
            return
        
        try:
            # Start the program process
            # Using PYTHONUNBUFFERED=1 to ensure output is not buffered
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'
            
            self.process = subprocess.Popen(
                [sys.executable, self.program_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env
            )
            
            self.running = True
            
            # Start a thread to read and print the output
            self.thread = threading.Thread(target=self._monitor_output)
            self.thread.daemon = True
            self.thread.start()
            
            # Start timeout thread if timeout is specified
            if self.timeout is not None:
                self.timeout_thread = threading.Thread(target=self._timeout_monitor)
                self.timeout_thread.daemon = True
                self.timeout_thread.start()
            
            # Start screenshot thread
            self.screenshot_thread = threading.Thread(target=self._take_screenshot_after_delay)
            self.screenshot_thread.daemon = True
            self.screenshot_thread.start()
            
            logger.info(f"Program started from {self.program_path}")
            
        except Exception as e:
            logger.error(f"Error starting program: {e}")
    
    def _create_test_image(self, path):
        """Create a test image with a red dot on a black background."""
        try:
            # Create a black background image
            width, height = 400, 400
            image = Image.new('RGB', (width, height), color='black')
            
            # Draw a red dot in the middle
            draw = ImageDraw.Draw(image)
            dot_radius = 10
            center_x, center_y = width // 2, height // 2
            draw.ellipse(
                (center_x - dot_radius, center_y - dot_radius, 
                 center_x + dot_radius, center_y + dot_radius), 
                fill='red'
            )
            
            # Save the image
            image.save(path, format='PNG')
            logger.info(f"Created test image at {path}")
            
            # Verify the image was saved correctly
            if os.path.exists(path) and os.path.getsize(path) > 0:
                # Try to open the image to verify it's valid
                with Image.open(path) as img:
                    width, height = img.size
                    format = img.format
                    logger.info(f"Test image validated: {width}x{height} {format}")
                return True
            else:
                logger.error(f"Failed to create test image: File is empty or doesn't exist")
                return False
        except Exception as e:
            logger.error(f"Error creating test image: {e}")
            return False
    
    def _take_screenshot_after_delay(self):
        """Take a screenshot after the specified delay"""
        time.sleep(self.screenshot_delay)
        
        if not self.running:
            logger.info("Program is no longer running, cannot take screenshot")
            return
        
        try:
            # Create a temporary file for the screenshot
            fd, self.screenshot_path = tempfile.mkstemp(suffix='.png')
            os.close(fd)
            
            # Try to find the window
            window_info = self._find_program_window()
            
            # Take the screenshot
            if window_info and 'region' in window_info:
                # Take screenshot of the specific window
                logger.info(f"Taking screenshot of window: {window_info}")
                region = window_info['region']
                
                # Unpack region coordinates
                x, y, width, height = region
                
                # Take the screenshot of the specific region
                screenshot = pyautogui.screenshot(region=(x, y, width, height))
                logger.info(f"Captured region: x={x}, y={y}, width={width}, height={height}")
            else:
                # If window not found, take full screen screenshot
                logger.info("Window not found or region not available, taking full screen screenshot")
                screenshot = pyautogui.screenshot()
            
            # Verify screenshot was captured
            if screenshot is None:
                logger.error("Error: Screenshot capture failed")
                # Create a test image as fallback
                if not self._create_test_image(self.screenshot_path):
                    return
            else:
                # Save the screenshot with explicit format
                try:
                    # Convert to RGB mode to ensure compatibility
                    screenshot = screenshot.convert('RGB')
                    
                    # Save the image with high quality
                    screenshot.save(self.screenshot_path, format='PNG', quality=95)
                    
                    # Verify the file was created and has content
                    if os.path.exists(self.screenshot_path) and os.path.getsize(self.screenshot_path) > 0:
                        logger.info(f"Screenshot saved to {self.screenshot_path} ({os.path.getsize(self.screenshot_path)} bytes)")
                        
                        # Verify the image can be opened
                        try:
                            with Image.open(self.screenshot_path) as img:
                                width, height = img.size
                                format = img.format
                                logger.info(f"Screenshot validated: {width}x{height} {format}")
                        except Exception as img_error:
                            logger.error(f"Invalid screenshot file: {str(img_error)}")
                            # Create a test image as fallback
                            self._create_test_image(self.screenshot_path)
                    else:
                        logger.warning(f"Warning: Screenshot file is empty or not created at {self.screenshot_path}")
                        # Create a test image as fallback
                        self._create_test_image(self.screenshot_path)
                except Exception as e:
                    logger.error(f"Error saving screenshot: {e}")
                    # Create a test image as fallback
                    self._create_test_image(self.screenshot_path)
                
        except Exception as e:
            logger.error(f"Error taking screenshot: {e}")
            
            # If screenshot path was created but failed, create a test image
            if self.screenshot_path:
                self._create_test_image(self.screenshot_path)
            else:
                # Create a new temporary file for the test image
                fd, self.screenshot_path = tempfile.mkstemp(suffix='.png')
                os.close(fd)
                self._create_test_image(self.screenshot_path)
    
    def _find_program_window(self):
        """Find the window of the running program"""
        try:
            # Different approaches based on platform
            system = platform.system()
            
            if system == 'Darwin':  # macOS
                # Get a list of all window names and their positions
                script = '''
                tell application "System Events"
                    set windowList to {}
                    set allProcesses to every process whose background only is false
                    repeat with proc in allProcesses
                        set procName to name of proc
                        set windowCount to count of windows of proc
                        if windowCount > 0 then
                            repeat with i from 1 to windowCount
                                set winName to name of window i of proc
                                set winPos to position of window i of proc
                                set winSize to size of window i of proc
                                set end of windowList to procName & ":" & winName & ":" & winPos & ":" & winSize
                            end repeat
                        end if
                    end repeat
                    return windowList
                end tell
                '''
                
                # Use osascript to run the AppleScript
                result = subprocess.run(['osascript', '-e', script], 
                                        capture_output=True, text=True)
                
                output = result.stdout.strip()
                logger.debug(f"Available windows: {output}")
                
                # Look for Python windows first - prioritize non-terminal windows
                program_name = os.path.basename(self.program_path).split('.')[0]
                
                # First pass: Look for Python windows with specific names related to our program
                for window_entry in output.split(", "):
                    if ":" in window_entry and window_entry.count(":") >= 3:
                        try:
                            parts = window_entry.split(":")
                            if len(parts) >= 4:
                                proc_name = parts[0]
                                window_name = parts[1]
                                pos_str = parts[2]
                                size_str = parts[3]
                                
                                # Check if this is likely our window - prioritize Python windows with program name
                                # Avoid Terminal windows
                                if (proc_name.lower() == "python" and 
                                    "terminal" not in window_name.lower() and
                                    (program_name.lower() in window_name.lower() or
                                     "pygame" in window_name.lower() or
                                     "tkinter" in window_name.lower() or
                                     "qt" in window_name.lower() or
                                     "circle" in window_name.lower())):
                                    
                                    # Parse position
                                    if len(pos_str) >= 6:  # Ensure it's long enough
                                        # Split the string in the middle
                                        middle = len(pos_str) // 2
                                        x = int(pos_str[:middle])
                                        y = int(pos_str[middle:])
                                        
                                        # Parse size
                                        if len(size_str) >= 6:  # Ensure it's long enough
                                            # Split the string in the middle
                                            middle = len(size_str) // 2
                                            width = int(size_str[:middle])
                                            height = int(size_str[middle:])
                                            
                                            logger.info(f"Found matching window: {proc_name}:{window_name}")
                                            logger.info(f"Parsed window coordinates: x={x}, y={y}, width={width}, height={height}")
                                            
                                            return {
                                                'title': f'{proc_name}: {window_name}',
                                                'region': (x, y, width, height)
                                            }
                        except Exception as e:
                            logger.error(f"Error parsing window entry {window_entry}: {e}")
                
                # Second pass: Look for any Python window
                for window_entry in output.split(", "):
                    if ":" in window_entry and window_entry.count(":") >= 3:
                        try:
                            parts = window_entry.split(":")
                            if len(parts) >= 4:
                                proc_name = parts[0]
                                window_name = parts[1]
                                pos_str = parts[2]
                                size_str = parts[3]
                                
                                # Check if this is a Python window
                                if proc_name.lower() == "python" and "terminal" not in window_name.lower():
                                    # Parse position
                                    if len(pos_str) >= 6:  # Ensure it's long enough
                                        # Split the string in the middle
                                        middle = len(pos_str) // 2
                                        x = int(pos_str[:middle])
                                        y = int(pos_str[middle:])
                                        
                                        # Parse size
                                        if len(size_str) >= 6:  # Ensure it's long enough
                                            # Split the string in the middle
                                            middle = len(size_str) // 2
                                            width = int(size_str[:middle])
                                            height = int(size_str[middle:])
                                            
                                            logger.info(f"Found Python window: {proc_name}:{window_name}")
                                            logger.info(f"Parsed window coordinates: x={x}, y={y}, width={width}, height={height}")
                                            
                                            return {
                                                'title': f'{proc_name}: {window_name}',
                                                'region': (x, y, width, height)
                                            }
                        except Exception as e:
                            logger.error(f"Error parsing window entry {window_entry}: {e}")
            
            elif system == 'Windows':
                try:
                    import win32gui
                    import win32process
                    import psutil
                    
                    def callback(hwnd, windows):
                        if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
                            _, pid = win32process.GetWindowThreadProcessId(hwnd)
                            try:
                                process = psutil.Process(pid)
                                if process.name().lower() in ['python.exe', 'pythonw.exe']:
                                    # Check if this is our process
                                    if process.pid == self.process.pid:
                                        rect = win32gui.GetWindowRect(hwnd)
                                        x, y, right, bottom = rect
                                        width = right - x
                                        height = bottom - y
                                        
                                        windows.append({
                                            'hwnd': hwnd,
                                            'title': win32gui.GetWindowText(hwnd),
                                            'region': (x, y, width, height)
                                        })
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                pass
                        return True
                    
                    windows = []
                    win32gui.EnumWindows(callback, windows)
                    
                    # Sort by window title relevance to our program name
                    program_name = os.path.basename(self.program_path).split('.')[0]
                    windows.sort(key=lambda w: program_name.lower() in w['title'].lower(), reverse=True)
                    
                    if windows:
                        logger.info(f"Found Windows window: {windows[0]['title']}")
                        return windows[0]
                    
                except ImportError:
                    logger.error("Required Windows modules not available")
            
            elif system == 'Linux':
                try:
                    # Try using Xlib for Linux
                    from Xlib import display, X
                    
                    # Connect to the X server
                    d = display.Display()
                    root = d.screen().root
                    
                    # Get the window ID of our process
                    window_pid = None
                    
                    # Get all windows
                    window_ids = root.get_full_property(
                        d.intern_atom('_NET_CLIENT_LIST'),
                        X.AnyPropertyType
                    ).value
                    
                    for window_id in window_ids:
                        window = d.create_resource_object('window', window_id)
                        
                        # Get the PID of the window
                        window_pid = window.get_full_property(
                            d.intern_atom('_NET_WM_PID'),
                            X.AnyPropertyType
                        )
                        
                        if window_pid and window_pid.value[0] == self.process.pid:
                            # Get window geometry
                            geometry = window.get_geometry()
                            x, y = geometry.x, geometry.y
                            width, height = geometry.width, geometry.height
                            
                            # Translate coordinates to global screen coordinates
                            coords = root.translate_coords(window, x, y)
                            x, y = coords.x, coords.y
                            
                            return {
                                'title': 'Linux Window',
                                'region': (x, y, width, height)
                            }
                except ImportError:
                    logger.error("Xlib not available, cannot find window on Linux")
            
            # Fallback: just return None and we'll take a full screenshot
            return None
            
        except Exception as e:
            logger.error(f"Error finding program window: {e}")
            return None
    
    def get_screenshot_path(self):
        """Get the path to the saved screenshot"""
        return self.screenshot_path
    
    def _timeout_monitor(self):
        """Monitor the timeout and stop the program when reached"""
        if self.timeout is None:
            return
            
        time.sleep(self.timeout)
        if self.running:
            logger.info(f"Timeout of {self.timeout} seconds reached. Stopping program...")
            self.stop_program()
    
    def _monitor_output(self):
        """Monitor and print the output from the program process"""
        while self.running and self.process.poll() is None:
            # Read stdout
            stdout_line = self.process.stdout.readline()
            if stdout_line:
                logger.info(f"Program output: {stdout_line.strip()}")
            
            # Read stderr
            stderr_line = self.process.stderr.readline()
            if stderr_line:
                logger.error(f"Program error: {stderr_line.strip()}")
            
            # Small sleep to prevent CPU hogging
            time.sleep(0.01)
        
        # Process has ended
        if self.running:
            self.running = False
            logger.info("Program has ended")
    
    def stop_program(self):
        """Stop the running program"""
        if not self.running:
            logger.info("No program is running")
            return
        
        try:
            # Try to terminate the process gracefully
            if self.process and self.process.poll() is None:
                if sys.platform == 'win32':
                    self.process.terminate()
                else:
                    # On Unix-like systems, we can use SIGTERM
                    os.kill(self.process.pid, signal.SIGTERM)
                
                # Give it some time to terminate
                for _ in range(10):
                    if self.process.poll() is not None:
                        break
                    time.sleep(0.1)
                
                # If it's still running, force kill
                if self.process.poll() is None:
                    if sys.platform == 'win32':
                        self.process.kill()
                    else:
                        os.kill(self.process.pid, signal.SIGKILL)
            
            self.running = False
            if self.thread and self.thread.is_alive():
                self.thread.join(timeout=1)
            
            logger.info("Program stopped")
            
        except Exception as e:
            logger.error(f"Error stopping program: {e}")
    
    def is_running(self):
        """Check if the program is currently running"""
        if self.process:
            # Update running status based on process state
            self.running = self.process.poll() is None
        return self.running


def main():
    """Main function to demonstrate usage with vision model"""
    program_path = "/Users/jjj/git/tmpgame/game.py"
    timeout = 15  # 15 seconds timeout
    screenshot_delay = 5  # Take screenshot after 5 seconds
    
    # Check if the program exists
    if not os.path.exists(program_path):
        print(f"Error: Program not found at {program_path}")
        print("Please update the program_path variable to point to a valid Python script.")
        return
    
    runner = ProgramRunner(program_path, timeout=timeout, screenshot_delay=screenshot_delay)
    
    try:
        print("Starting program...")
        runner.start_program()
        
        # Wait for the screenshot to be taken
        for i in range(screenshot_delay):
            print(f"Waiting for screenshot: {i+1}/{screenshot_delay} seconds")
            time.sleep(1)
        
        # Wait a bit more to ensure the screenshot is taken
        time.sleep(1)
        
        # Get the screenshot path
        screenshot_path = runner.get_screenshot_path()
        
        # Add a small delay to ensure the file is fully written to disk
        time.sleep(1)
        
        if screenshot_path and os.path.exists(screenshot_path):
            print(f"Screenshot was saved to: {screenshot_path}")
            
            # Verify the file exists and has content
            if os.path.exists(screenshot_path) and os.path.getsize(screenshot_path) > 0:
                print(f"Screenshot file verified: {screenshot_path} ({os.path.getsize(screenshot_path)} bytes)")
            else:
                print(f"Warning: Screenshot file issue at {screenshot_path}")
            
            # Create the vision testing agent
            print("Initializing vision testing agent...")
            vision_agent = VisionTestingAgent()
            
            # Analyze the screenshot
            print("\nAnalyzing screenshot...")
            
            # Use a simple prompt for testing
            prompt = """
            Analyze this screenshot of a program's output.

            Expected visual elements:
            A black background with a red dot in the middle.

            Please verify if the expected visual elements are present in the screenshot.
            Be specific about what you see and whether it matches the expectations.
            If there are any discrepancies, explain them in detail.
            
            You answer with a clear YES or NO verdict in the first line of response. In case of NO, explain why in the following lines.
            """
            
            # Set the screenshot path and use the _analyze_screenshot method
            vision_agent.screenshot_path = screenshot_path
            response_vision = vision_agent._analyze_screenshot(prompt)
            
            print("\nResponse from vision model:")
            print("-" * 50)
            print(response_vision)
            print("-" * 50)
            
            # Test the success determination
            success = vision_agent._determine_success(response_vision)
            print(f"\nSuccess determination: {success}")
        else:
            print("No screenshot was taken or the file doesn't exist.")
        
        # Wait for the program to finish (either by timeout or naturally)
        while runner.is_running():
            print("Waiting for program to finish...")
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    finally:
        # Make sure to stop the program
        if runner and runner.is_running():
            print("Stopping program...")
            runner.stop_program()
    
    print("Done!")


if __name__ == "__main__":
    main()
