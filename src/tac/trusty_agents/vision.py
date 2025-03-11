#!/usr/bin/env python3
import subprocess
import threading
import time
import os
import signal
import sys
import pyautogui
from PIL import Image
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
            
            # Save the screenshot
            screenshot.save(self.screenshot_path)
            print(f"Screenshot saved to {self.screenshot_path}")
            
        except Exception as e:
            print(f"Error taking screenshot: {e}")
    
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
                
                # First approach: Try to find window by PID
                # This is the most reliable method as it directly matches our process
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
                
                # Second approach: Parse the raw output to find our window
                # Look for windows with "python" in the name or matching our program name
                program_name = os.path.basename(self.program_path).split('.')[0]
                
                for window_entry in output.split(", "):
                    if ":" in window_entry and window_entry.count(":") >= 3:
                        try:
                            parts = window_entry.split(":")
                            if len(parts) >= 4:
                                proc_name = parts[0]
                                window_name = parts[1]
                                pos_str = parts[2]
                                size_str = parts[3]
                                
                                # Check if this is likely our window
                                if (proc_name.lower() == "python" or 
                                    program_name.lower() in window_name.lower() or
                                    "circle" in window_name.lower()):  # For the Red Circle Game example
                                    
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
                
                # Third approach: Look for the most recently created window
                # This is a last resort
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


def main():
    """Main function to demonstrate usage"""
    program_path = "/Users/jjj/git/tmpgame/game.py"
    timeout = 10  # 10 seconds timeout
    screenshot_delay = 5  # Take screenshot after 5 seconds
    
    runner = ProgramRunner(program_path, timeout=timeout, screenshot_delay=screenshot_delay)
    
    print("Starting program...")
    runner.start_program()
    
    # We can do other things while the program is running
    for i in range(5):
        print(f"Main thread is still active: {i}")
        time.sleep(1)
    
    # Wait for the program to finish (either by timeout or naturally)
    while runner.is_running():
        time.sleep(0.5)
    
    # Get the screenshot path
    screenshot_path = runner.get_screenshot_path()
    if screenshot_path:
        print(f"Screenshot was saved to: {screenshot_path}")
    
    print("Done!")


if __name__ == "__main__":
    main()
