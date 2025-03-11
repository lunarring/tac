#!/usr/bin/env python3
import subprocess
import threading
import time
import os
import signal
import sys

class ProgramRunner:
    def __init__(self, program_path, timeout=None):
        """
        Initialize the ProgramRunner with the path to the program script.
        
        Args:
            program_path (str): Path to the Python script to run
            timeout (int, optional): Timeout in seconds after which the program will be stopped.
                                    None means no timeout (run indefinitely until stopped manually).
        """
        self.program_path = program_path
        self.process = None
        self.running = False
        self.thread = None
        self.timeout = timeout
        self.timeout_thread = None
    
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
            
            print(f"Program started from {self.program_path}")
            
        except Exception as e:
            print(f"Error starting program: {e}")
    
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
    
    runner = ProgramRunner(program_path, timeout=timeout)
    
    print("Starting program...")
    runner.start_program()
    
    # We can do other things while the program is running
    for i in range(5):
        print(f"Main thread is still active: {i}")
        time.sleep(1)
    
    # The program will be automatically stopped after the timeout
    # But we could also stop it manually if needed:
    # print("Stopping program...")
    # runner.stop_program()
    
    # Wait for the program to finish (either by timeout or naturally)
    while runner.is_running():
        time.sleep(0.5)
    
    print("Done!")


if __name__ == "__main__":
    main()
