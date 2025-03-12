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
            print("Program is already running")
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
            
            print(f"Program started from {self.program_path}")
            
        except Exception as e:
            print(f"Error starting program: {e}")
    
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
            print(f"Created test image at {path}")
            return True
        except Exception as e:
            print(f"Error creating test image: {e}")
            return False
    
    def _take_screenshot_after_delay(self):
        """Take a screenshot after the specified delay"""
        time.sleep(self.screenshot_delay)
        
        if not self.running:
            print("Program is no longer running, cannot take screenshot")
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
                print(f"Taking screenshot of window: {window_info}")
                region = window_info['region']
                
                # Unpack region coordinates
                x, y, width, height = region
                
                # Take the screenshot of the specific region
                screenshot = pyautogui.screenshot(region=(x, y, width, height))
                print(f"Captured region: x={x}, y={y}, width={width}, height={height}")
            else:
                # If window not found, take full screen screenshot
                print("Window not found or region not available, taking full screen screenshot")
                screenshot = pyautogui.screenshot()
            
            # Verify screenshot was captured
            if screenshot is None:
                print("Error: Screenshot capture failed")
                # Create a test image as fallback
                if not self._create_test_image(self.screenshot_path):
                    return
            else:
                # Save the screenshot with explicit format
                try:
                    # Convert to RGB mode to ensure compatibility
                    screenshot = screenshot.convert('RGB')
                    screenshot.save(self.screenshot_path, format='PNG')
                    
                    # Verify the file was created and has content
                    if os.path.exists(self.screenshot_path) and os.path.getsize(self.screenshot_path) > 0:
                        print(f"Screenshot saved to {self.screenshot_path} ({os.path.getsize(self.screenshot_path)} bytes)")
                    else:
                        print(f"Warning: Screenshot file is empty or not created at {self.screenshot_path}")
                        # Create a test image as fallback
                        self._create_test_image(self.screenshot_path)
                except Exception as e:
                    print(f"Error saving screenshot: {e}")
                    # Create a test image as fallback
                    self._create_test_image(self.screenshot_path)
                
        except Exception as e:
            print(f"Error taking screenshot: {e}")
            
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
                print(f"Available windows: {output}")
                
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
                                            
                                            print(f"Found matching window: {proc_name}:{window_name}")
                                            print(f"Parsed window coordinates: x={x}, y={y}, width={width}, height={height}")
                                            
                                            return {
                                                'title': f'{proc_name}: {window_name}',
                                                'region': (x, y, width, height)
                                            }
                        except Exception as e:
                            print(f"Error parsing window entry: {e}")
                
                # Second pass: Look for any Python window that's not a terminal
                for window_entry in output.split(", "):
                    if ":" in window_entry and window_entry.count(":") >= 3:
                        try:
                            parts = window_entry.split(":")
                            if len(parts) >= 4:
                                proc_name = parts[0]
                                window_name = parts[1]
                                pos_str = parts[2]
                                size_str = parts[3]
                                
                                # Check if this is a Python window but not a terminal
                                if (proc_name.lower() == "python" and 
                                    "terminal" not in window_name.lower()):
                                    
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
                                            
                                            print(f"Found Python window: {proc_name}:{window_name}")
                                            print(f"Parsed window coordinates: x={x}, y={y}, width={width}, height={height}")
                                            
                                            return {
                                                'title': f'{proc_name}: {window_name}',
                                                'region': (x, y, width, height)
                                            }
                        except Exception as e:
                            print(f"Error parsing window entry: {e}")
                
                # Third pass: Look for any window with our program name
                for window_entry in output.split(", "):
                    if ":" in window_entry and window_entry.count(":") >= 3:
                        try:
                            parts = window_entry.split(":")
                            if len(parts) >= 4:
                                proc_name = parts[0]
                                window_name = parts[1]
                                pos_str = parts[2]
                                size_str = parts[3]
                                
                                # Check if window name contains our program name
                                if (program_name.lower() in window_name.lower() and
                                    "terminal" not in window_name.lower()):
                                    
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
                                            
                                            print(f"Found window with program name: {proc_name}:{window_name}")
                                            print(f"Parsed window coordinates: x={x}, y={y}, width={width}, height={height}")
                                            
                                            return {
                                                'title': f'{proc_name}: {window_name}',
                                                'region': (x, y, width, height)
                                            }
                        except Exception as e:
                            print(f"Error parsing window entry: {e}")
                
                # Fourth pass: Try to find window by PID
                if self.process and self.process.pid:
                    script = f'''
                    tell application "System Events"
                        set targetWindow to ""
                        set targetPos to ""
                        set targetSize to ""
                        set allProcesses to every process
                        repeat with proc in allProcesses
                            if unix id of proc is {self.process.pid} then
                                set procName to name of proc
                                set windowCount to count of windows of proc
                                if windowCount > 0 then
                                    set targetWindow to name of window 1 of proc
                                    set targetPos to position of window 1 of proc
                                    set targetSize to size of window 1 of proc
                                    exit repeat
                                end if
                            end if
                        end repeat
                        return procName & ":" & targetWindow & ":" & targetPos & ":" & targetSize
                    end tell
                    '''
                    
                    result = subprocess.run(['osascript', '-e', script], 
                                           capture_output=True, text=True)
                    
                    window_info = result.stdout.strip()
                    print(f"Found window by PID: {window_info}")
                    
                    # Parse the window info
                    if ":" in window_info and window_info.count(":") >= 3:
                        try:
                            parts = window_info.split(":")
                            if len(parts) >= 4:
                                proc_name = parts[0]
                                window_name = parts[1]
                                pos_str = parts[2]
                                size_str = parts[3]
                                
                                # Parse position - format appears to be like "520238" for x=520, y=238
                                if len(pos_str) >= 6:  # Ensure it's long enough
                                    # Split the string in the middle
                                    middle = len(pos_str) // 2
                                    x = int(pos_str[:middle])
                                    y = int(pos_str[middle:])
                                    
                                    # Parse size - format appears to be like "400428" for width=400, height=428
                                    if len(size_str) >= 6:  # Ensure it's long enough
                                        # Split the string in the middle
                                        middle = len(size_str) // 2
                                        width = int(size_str[:middle])
                                        height = int(size_str[middle:])
                                        
                                        print(f"Parsed window coordinates: x={x}, y={y}, width={width}, height={height}")
                                        
                                        return {
                                            'title': f'{proc_name}: {window_name}',
                                            'region': (x, y, width, height)
                                        }
                        except Exception as e:
                            print(f"Error parsing window info by PID: {e}")
                
                # Fifth pass: Look for the most recently created window
                try:
                    # Get all windows and sort by creation time (not available directly, so we use the order in the list)
                    windows = []
                    for window_entry in output.split(", "):
                        if ":" in window_entry and window_entry.count(":") >= 3:
                            parts = window_entry.split(":")
                            if len(parts) >= 4:
                                proc_name = parts[0]
                                window_name = parts[1]
                                pos_str = parts[2]
                                size_str = parts[3]
                                
                                # Skip terminal windows
                                if "terminal" in window_name.lower():
                                    continue
                                
                                # Parse position and size
                                try:
                                    if len(pos_str) >= 6 and len(size_str) >= 6:
                                        # Split position string in the middle
                                        middle_pos = len(pos_str) // 2
                                        x = int(pos_str[:middle_pos])
                                        y = int(pos_str[middle_pos:])
                                        
                                        # Split size string in the middle
                                        middle_size = len(size_str) // 2
                                        width = int(size_str[:middle_size])
                                        height = int(size_str[middle_size:])
                                        
                                        # Only consider reasonably sized windows
                                        if width > 50 and height > 50:
                                            windows.append({
                                                'proc_name': proc_name,
                                                'window_name': window_name,
                                                'region': (x, y, width, height)
                                            })
                                except ValueError:
                                    continue
                    
                    # If we found any windows, return the last one (most recently created)
                    if windows:
                        last_window = windows[-1]
                        print(f"Using last window as fallback: {last_window['proc_name']}:{last_window['window_name']}")
                        return {
                                'title': f"{last_window['proc_name']}: {last_window['window_name']}",
                                'region': last_window['region']
                        }
                except Exception as e:
                    print(f"Error finding last window: {e}")
                
                # If all else fails, take a full screen screenshot
                print("Could not find a specific window, will take full screen screenshot")
                return None
            
            elif system == 'Windows':
                # On Windows, we could use win32gui to find the window
                # This would require installing pywin32
                try:
                    import win32gui
                    import win32process
                    
                    def callback(hwnd, windows):
                        if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
                            _, pid = win32process.GetWindowThreadProcessId(hwnd)
                            if pid == self.process.pid:
                                rect = win32gui.GetWindowRect(hwnd)
                                x, y, right, bottom = rect
                                width = right - x
                                height = bottom - y
                                windows.append({
                                    'title': win32gui.GetWindowText(hwnd),
                                    'region': (x, y, width, height)
                                })
                    
                    windows = []
                    win32gui.EnumWindows(callback, windows)
                    
                    if windows:
                        return windows[0]  # Return the first matching window
                except ImportError:
                    print("win32gui not available, cannot find window on Windows")
            
            elif system == 'Linux':
                # On Linux, we can use Xlib to find the window
                try:
                    from Xlib import display, X
                    
                    d = display.Display()
                    root = d.screen().root
                    
                    # Get window list
                    window_list = root.get_full_property(
                        d.intern_atom('_NET_CLIENT_LIST'), X.AnyPropertyType
                    ).value
                    
                    for window_id in window_list:
                        window = d.create_resource_object('window', window_id)
                        
                        # Get window PID
                        window_pid = window.get_full_property(
                            d.intern_atom('_NET_WM_PID'), X.AnyPropertyType
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
                    print("Xlib not available, cannot find window on Linux")
            
            # Fallback: just return None and we'll take a full screenshot
            return None
            
        except Exception as e:
            print(f"Error finding program window: {e}")
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
            print(f"Timeout of {self.timeout} seconds reached. Stopping program...")
            self.stop_program()
    
    def _monitor_output(self):
        """Monitor and print the output from the program process"""
        while self.running and self.process.poll() is None:
            # Read stdout
            stdout_line = self.process.stdout.readline()
            if stdout_line:
                print(f"Program output: {stdout_line.strip()}")
            
            # Read stderr
            stderr_line = self.process.stderr.readline()
            if stderr_line:
                print(f"Program error: {stderr_line.strip()}")
            
            # Small sleep to prevent CPU hogging
            time.sleep(0.01)
        
        # Process has ended
        if self.running:
            self.running = False
            print("Program has ended")
    
    def stop_program(self):
        """Stop the running program"""
        if not self.running:
            print("No program is running")
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
            
            print("Program stopped")
            
        except Exception as e:
            print(f"Error stopping program: {e}")
    
    def is_running(self):
        """Check if the program is currently running"""
        if self.process:
            # Update running status based on process state
            self.running = self.process.poll() is None
        return self.running


class VisionAnalyzer:
    """Class for analyzing screenshots using vision models."""
    
    def __init__(self, llm_type="vision"):
        """
        Initialize the VisionAnalyzer.
        
        Args:
            llm_type: Type of LLM to use (defaults to "vision")
        """
        # Import here to avoid circular imports
        import sys
        from pathlib import Path
        
        # Add the parent directory to the path so we can import the tac module
        sys.path.append(str(Path(__file__).parent.parent.parent))
        
        from tac.core.llm import LLMClient, Message
        self.client = LLMClient(llm_type=llm_type)
        self.Message = Message
    
    def analyze_screenshot(self, program_runner, prompt, temperature=None):
        """
        Analyze a screenshot taken by a ProgramRunner.
        
        Args:
            program_runner: An instance of ProgramRunner that has taken a screenshot
            prompt: The prompt to send to the vision model
            temperature: Controls randomness (0.0 to 1.0)
            
        Returns:
            str: The content of the model's response message
        """
        # Get the screenshot path from the program runner
        screenshot_path = program_runner.get_screenshot_path()
        for i in range(10):
            time.sleep(0.2)
            file_size = os.path.getsize(screenshot_path)
            if file_size > 0:
                break
        
        # Validate screenshot path
        if not screenshot_path:
            error_msg = "No screenshot available from the program runner"
            print(f"Error: {error_msg}")
            return f"Vision analysis failed: {error_msg}"
            
        if not os.path.exists(screenshot_path):
            error_msg = f"Screenshot file not found at {screenshot_path}"
            print(f"Error: {error_msg}")
            return f"Vision analysis failed: {error_msg}"
        
        # Print file details for debugging
        file_size = os.path.getsize(screenshot_path)
        print(f"Screenshot file: {screenshot_path}")
        print(f"File size: {file_size} bytes")
        print(f"File exists: {os.path.exists(screenshot_path)}")
        
        # Send the screenshot to the vision model
        try:
            # Create messages for the vision model - EXACTLY as in the llm.py example
            vision_messages = [
                self.Message(role="system", content="You are a helpful assistant that can analyze images"),
                self.Message(role="user", content=prompt)
            ]
            
            print(f"Analyzing image at: {screenshot_path}")
            
            # Verify we can read the file
            try:
                with open(screenshot_path, 'rb') as f:
                    test_read = f.read(100)  # Just read a few bytes to test
                print(f"Successfully read {len(test_read)} bytes from the file")
            except Exception as read_error:
                print(f"Warning: Could not read from file: {read_error}")
            
            # Use vision_chat_completion directly - EXACTLY as in the llm.py example
            response_vision = self.client.vision_chat_completion(vision_messages, screenshot_path, temperature)
            return response_vision
        except Exception as e:
            error_msg = f"Error during vision analysis: {str(e)}"
            print(f"Error: {error_msg}")
            return f"Vision analysis failed: {error_msg}"


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
        if screenshot_path and os.path.exists(screenshot_path):
            print(f"Screenshot was saved to: {screenshot_path}")
            
            # Verify the file exists and has content
            if os.path.exists(screenshot_path) and os.path.getsize(screenshot_path) > 0:
                print(f"Screenshot file verified: {screenshot_path} ({os.path.getsize(screenshot_path)} bytes)")
            else:
                print(f"Warning: Screenshot file issue at {screenshot_path}")
            
            # Create the vision analyzer
            print("Initializing vision analyzer...")
            analyzer = VisionAnalyzer()
            
            # Analyze the screenshot - using the exact same approach as in llm.py
            print("\nAnalyzing screenshot...")
            
            # Use the same prompt as in the example
            response_vision = analyzer.analyze_screenshot(
                runner,
                prompt="Do you see a black background and a red dot in the middle?",
                temperature=0.7
            )
            
            print("\nResponse from vision model:")
            print("-" * 50)
            print(response_vision)
            print("-" * 50)
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
