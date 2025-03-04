#!/usr/bin/env python
import os
import sys
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from datetime import datetime
import re
import glob

# Import getch at the top level since we'll use it throughout
try:
    import getch
    def get_single_key():
        return getch.getch().decode('utf-8')
except ImportError:
    # Fallback if getch is not available
    import sys
    import tty
    import termios
    
    def get_single_key():
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch.lower()

# Simple print function for errors
def log_error(msg):
    print(f"ERROR - {msg} [tac.cli.viewer]", file=sys.stderr)

class TACViewer:
    def __init__(self):
        # Disable syntax highlighting by setting highlight=False
        self.console = Console(highlight=False)
        self.history = []  # Stack to track menu history and their arguments
        self.items_per_page = 10  # Number of items to show per page
        self.lines_per_page = 25  # Increased number of lines per page for log viewing
        self.current_log_path = None
        self.current_log_content = []

    def get_human_time_diff(self, timestamp: float) -> str:
        """Convert a timestamp into a human-friendly time difference string."""
        now = datetime.now().timestamp()
        diff = now - timestamp
        
        if diff < 60:  # Less than a minute
            return "just now"
        elif diff < 3600:  # Less than an hour
            mins = int(diff / 60)
            return f"{mins}min ago"
        elif diff < 86400:  # Less than a day
            hours = diff / 3600
            return f"{hours:.1f}hours ago"
        else:
            days = diff / 86400
            return f"{days:.1f}days ago"
            
    def show_menu(self, options: list, title: str = None, show_nav: bool = False, has_next: bool = False, has_prev: bool = False) -> None:
        """Display a menu with numbered options."""
        if title:
            self.console.print(f"\n[bold cyan]{title}[/bold cyan]")
        self.console.print("\nChoose an option:")
        for i, option in enumerate(options, 1):
            self.console.print(f"{i}. {option}")
        if show_nav:
            if has_prev:
                self.console.print("p. Previous page")
            if has_next:
                self.console.print("n. Next page")
        if self.history:  # Show back option only if we have history
            self.console.print("b. Back")
        self.console.print("q. Quit")
        
    def get_choice(self, max_choice: int, allow_nav: bool = False, has_next: bool = False, has_prev: bool = False) -> str:
        """Get user choice with single-key input."""
        while True:
            self.console.print("\nPress a key to choose...")
            choice = get_single_key()
            
            if choice == 'q':
                sys.exit(0)
            if choice == 'b' and self.history:
                return 'b'
            if allow_nav:
                if choice == 'n' and has_next:
                    return 'n'
                if choice == 'p' and has_prev:
                    return 'p'
            try:
                # For number choices, collect digits until a non-digit is pressed
                if choice.isdigit():
                    num = int(choice)
                    if 1 <= num <= max_choice:
                        return num
            except ValueError:
                pass
            self.console.print("[red]Invalid choice. Please try again.[/red]")
            
    def add_to_history(self, menu_func, *args):
        """Add a menu function and its arguments to history."""
        self.history.append((menu_func, args))
            
    def go_back(self):
        """Go back to the previous menu."""
        if self.history:
            menu_func, args = self.history.pop()
            # Instead of calling the menu function directly, return to let the current menu exit
            return True
        return False
            
    def main_menu(self) -> None:
        """Show main menu to choose between logs."""
        while True:
            options = ["View Logs"]
            self.show_menu(options, "TAC Log Viewer")
            choice = self.get_choice(len(options))
            
            if choice == 'b':
                if self.go_back():  # Only break the loop if we actually went back
                    break
                continue
                
            self.add_to_history(self.main_menu)
            if choice == 1:
                self.logs_menu()
                
    def list_logs(self):
        """List all available log files in the logs directory."""
        logs_dir = '.tac_logs'
        if not os.path.exists(logs_dir):
            return []
        
        log_files = glob.glob(os.path.join(logs_dir, '*_log.txt'))
        return sorted(log_files, key=os.path.getmtime, reverse=True)
                
    def logs_menu(self) -> None:
        """Show menu with available log files."""
        page = 0  # Start at first page
        while True:
            logs = self.list_logs()
            if not logs:
                self.console.print("[yellow]No log files found.[/yellow]")
                input("Press Enter to continue...")
                return

            # Calculate pagination
            start_idx = page * self.items_per_page
            end_idx = start_idx + self.items_per_page
            current_logs = logs[start_idx:end_idx]
            total_pages = (len(logs) + self.items_per_page - 1) // self.items_per_page

            # Create options with human-friendly times
            options = []
            for log in current_logs:
                mtime = os.path.getmtime(log)
                time_diff = self.get_human_time_diff(mtime)
                log_name = os.path.basename(log)
                options.append(f"{log_name} ({time_diff})")

            has_prev = page > 0
            has_next = end_idx < len(logs)

            self.show_menu(
                options, 
                f"Available Log Files (Page {page + 1}/{total_pages})",
                show_nav=True,
                has_next=has_next,
                has_prev=has_prev
            )
            choice = self.get_choice(len(options), allow_nav=True, has_next=has_next, has_prev=has_prev)

            if choice == 'b':
                if self.go_back():
                    break
                continue

            # Handle pagination navigation
            if choice == 'p' and has_prev:
                page -= 1
                continue
            if choice == 'n' and has_next:
                page += 1
                continue

            # Handle log selection
            if 1 <= choice <= len(current_logs):
                self.current_log_path = current_logs[choice - 1]
                if self.read_log(self.current_log_path):
                    self.display_log_content(self.current_log_content, f"Log File: {os.path.basename(self.current_log_path)}")
                    page = 0  # Reset page when returning to log list
    
    def read_log(self, log_path):
        """Read a log file and store its contents."""
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                self.current_log_content = f.readlines()
            return True
        except Exception as e:
            log_error(f"Error reading log file {log_path}: {str(e)}")
            self.current_log_content = []
            return False
    
    def log_menu(self) -> None:
        """Show log file contents."""
        self.display_log_content(self.current_log_content)
        
    def display_filtered_logs(self, level):
        """Display logs filtered by level."""
        filtered_logs = [line for line in self.current_log_content if level in line]
        self.display_log_content(filtered_logs, f"{level} Log Entries ({len(filtered_logs)} entries)")
    
    def search_logs(self):
        """Search logs for a specific term."""
        self.console.print("\nEnter search term (press any non-letter key when done):")
        search_term = ""
        while True:
            key = get_single_key()
            if key.isalpha() or key.isspace():
                search_term += key
                self.console.print(key, end="")
            else:
                break
                
        if not search_term:
            return
            
        filtered_logs = [line for line in self.current_log_content if search_term.lower() in line.lower()]
        self.display_log_content(filtered_logs, f"Search Results for '{search_term}' ({len(filtered_logs)} matches)")
    
    def display_log_content(self, log_content, title="Log Contents"):
        """Display log content in a paged view with single-key navigation."""
        page = 0
        
        while True:
            # Get terminal size and calculate available lines
            terminal_height = os.get_terminal_size().lines
            # Account for title (2 lines) and navigation (2 lines)
            lines_per_page = terminal_height - 4
            
            start_idx = page * lines_per_page
            end_idx = start_idx + lines_per_page
            current_lines = log_content[start_idx:end_idx]
            
            if not current_lines:
                self.console.print("[yellow]No log entries to display.[/yellow]")
                self.console.print("\nPress any key to continue...")
                get_single_key()
                return
                
            total_pages = (len(log_content) + lines_per_page - 1) // lines_per_page
            
            # Clear screen for better readability
            os.system('cls' if os.name == 'nt' else 'clear')
            
            self.console.print(f"\n[bold cyan]{title} (Page {page + 1}/{total_pages})[/bold cyan]")
            self.console.print(f"Showing lines {start_idx + 1}-{min(end_idx, len(log_content))} of {len(log_content)}")
            
            # Display log lines with syntax highlighting based on log level
            content_height = 0
            current_style = None
            
            for line in current_lines:
                # Check for the start of a new log entry
                if line.startswith(("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")):
                    if line.startswith("DEBUG"):
                        current_style = "blue"
                    elif line.startswith("INFO"):
                        current_style = "green"
                    elif line.startswith("WARNING"):
                        current_style = "yellow"
                    elif line.startswith("ERROR"):
                        current_style = "red"
                    elif line.startswith("CRITICAL"):
                        current_style = "red bold"
                
                # Print with current style if set, otherwise plain
                if current_style:
                    self.console.print(line.strip(), style=current_style)
                else:
                    self.console.print(line.strip())
                content_height += 1
            
            # Add padding to push navigation to bottom
            padding_needed = terminal_height - content_height - 4  # Account for header and nav
            if padding_needed > 0:
                self.console.print("\n" * (padding_needed - 1))
            
            # Single line navigation at the bottom
            nav_text = Text()
            nav_text.append("Navigate: ", style="bold")
            nav_text.append("[n]ext ", style="cyan" if end_idx < len(log_content) else "dim")
            nav_text.append("[b]ack ", style="cyan" if page > 0 else "dim")
            nav_text.append("[f]irst ", style="cyan")
            nav_text.append("[l]ast ", style="cyan")
            nav_text.append("[j]ump ", style="cyan")
            nav_text.append("[r]eturn ", style="cyan")
            nav_text.append("[q]uit", style="red")
            self.console.print(nav_text)
            
            choice = get_single_key().lower()
            
            if choice == 'q':
                sys.exit(0)
            elif choice == 'r':
                return
            elif choice == 'b' and page > 0:
                page -= 1
            elif choice == 'n' and end_idx < len(log_content):
                page += 1
            elif choice == 'f':
                page = 0
            elif choice == 'l':
                page = total_pages - 1
            elif choice == 'j':
                self.console.print("\nEnter page number and press any key when done:")
                page_str = ""
                while True:
                    key = get_single_key()
                    if key.isdigit():
                        page_str += key
                        self.console.print(key, end="")
                    else:
                        break
                try:
                    jump_page = int(page_str)
                    if 1 <= jump_page <= total_pages:
                        page = jump_page - 1
                    else:
                        self.console.print(f"\n[red]Invalid page number. Please enter a number between 1 and {total_pages}.[/red]")
                except ValueError:
                    self.console.print("\n[red]Invalid input. Please enter a number.[/red]")

def main():
    viewer = TACViewer()
    viewer.main_menu()

if __name__ == "__main__":
    main() 
