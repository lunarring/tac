#!/usr/bin/env python
import os
import sys
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from datetime import datetime
import re
import glob
import argparse  # Add argparse for command-line arguments
import time

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
                f"TAC Log Viewer - Available Log Files (Page {page + 1}/{total_pages})",
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
                    self.display_log_content(self.current_log_content, f"TAC Log Viewer - {os.path.basename(self.current_log_path)}")
                    page = 0  # Reset page when returning to log list
    
    def read_log(self, log_path):
        """Read a log file and store its contents."""
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                self.current_log_content = f.readlines()
            # Find all headings in the log file
            self.find_all_headings()
            return True
        except Exception as e:
            log_error(f"Error reading log file {log_path}: {str(e)}")
            self.current_log_content = []
            return False
    
    def find_all_headings(self):
        """Find all headings in the current log file and store them."""
        self.headings = []
        if not self.current_log_content:
            return
            
        # Pattern to identify heading sections (lines with multiple '=' characters)
        separator_pattern = re.compile(r'^=+$')  # One or more '=' characters
        
        i = 0
        while i < len(self.current_log_content):
            line = self.current_log_content[i].strip()
            
            # Check if this is a separator line
            if separator_pattern.match(line):
                # Found a potential start of heading section
                start_line = i
                
                # Look for the heading text and end separator
                if i + 1 < len(self.current_log_content):
                    heading_text = self.current_log_content[i + 1].strip()
                    
                    # Check if there's another separator line after the heading text
                    if i + 2 < len(self.current_log_content) and separator_pattern.match(self.current_log_content[i + 2].strip()):
                        # This is a confirmed heading section
                        # Add this heading to our list
                        self.headings.append({
                            'text': heading_text,
                            'line': i + 1,
                            'start_line': i
                        })
                        
                        # Skip past this heading section
                        i = i + 3
                        continue
            
            i += 1
    
    def get_current_heading(self, line_number):
        """Get the heading that applies to the current line number."""
        if not hasattr(self, 'headings') or not self.headings:
            return None
            
        # Find the most recent heading before the given line number
        current_heading = None
        for heading in self.headings:
            if heading['start_line'] <= line_number:
                current_heading = heading
            else:
                # We've gone past the current line, so use the previous heading
                break
                
        return current_heading
    
    def log_menu(self) -> None:
        """Show log file contents."""
        self.display_log_content(self.current_log_content)
        
    def display_filtered_logs(self, level):
        """Display logs filtered by level."""
        filtered_logs = [line for line in self.current_log_content if level in line]
        self.display_log_content(filtered_logs, f"{level} Log Entries ({len(filtered_logs)} entries)")
    
    def search_logs(self):
        """Search logs for a specific term."""
        self.console.print("\nEnter search term (press Enter to confirm, Esc to cancel):")
        search_term = ""
        while True:
            key = get_single_key()
            # Check for Enter (confirmation)
            if ord(key) in (10, 13):  # Enter key
                break
            # Check for Escape (cancel)
            elif ord(key) == 27:  # Escape key
                return
            # Check for backspace
            elif ord(key) in (8, 127):  # Backspace keys
                if search_term:
                    search_term = search_term[:-1]
                    # Move cursor back and clear the character
                    self.console.print("\b \b", end="")
            # Accept letters, numbers, and spaces
            elif key.isalnum() or key.isspace():
                search_term += key
                self.console.print(key, end="")
                
        if not search_term:
            return
            
        filtered_logs = [(line, search_term) for line in self.current_log_content if search_term.lower() in line.lower()]
        self.display_log_content(filtered_logs, f"Search Results for '{search_term}' ({len(filtered_logs)} matches)", is_search_result=True)
    
    def display_log_content(self, log_content, title="Log Contents", is_search_result=False):
        """Display log content in a paged view with single-key navigation."""
        page = 0
        # Maximum lines any single entry can take
        max_entry_height = 15
        
        while True:
            # Clear screen first
            os.system('cls' if os.name == 'nt' else 'clear')
            
            # Get terminal size
            terminal_height = os.get_terminal_size().lines
            terminal_width = os.get_terminal_size().columns
            
            # Calculate optimal number of content lines based on terminal height
            # Account for:
            # - Header: 4 lines (title, info, debug info, and current heading)
            # - Footer: 2 lines (blank line + navigation)
            # - Safety buffer: 1 line (minimal buffer)
            available_height = terminal_height - 4 - 2 - 1
            
            # Use at least 4 lines, at most 40 lines, but stay within available height
            max_display_lines = max(4, min(40, available_height))
            
            if not log_content:
                self.console.print("[yellow]No log entries to display.[/yellow]")
                self.console.print("\nPress any key to continue...")
                get_single_key()
                return
            
            # Calculate how many actual terminal lines each log entry will take
            entry_heights = []
            for i, item in enumerate(log_content):
                if is_search_result:
                    line, _ = item
                else:
                    line = item
                
                # Calculate how many lines this will take when rendered
                # Each line will wrap at terminal_width - 5 (small safety margin)
                effective_width = terminal_width - 5
                line_length = len(line.strip())
                lines_needed = max(1, (line_length + effective_width - 1) // effective_width)
                
                # Limit the height of any single entry to prevent very long entries from taking over
                lines_needed = min(lines_needed, max_entry_height)
                
                entry_heights.append((i, line, lines_needed))
            
            # Calculate page boundaries based on actual rendered heights
            page_boundaries = []
            current_page_start = 0
            current_height = 0
            
            for i, (idx, line, height) in enumerate(entry_heights):
                # If adding this entry would exceed the max display lines,
                # mark the end of the current page and start a new one
                if current_height + height > max_display_lines and current_height > 0:
                    page_boundaries.append((current_page_start, i - 1))
                    current_page_start = i
                    current_height = height
                else:
                    current_height += height
            
            # Add the last page if there are any remaining entries
            if current_page_start < len(entry_heights):
                page_boundaries.append((current_page_start, len(entry_heights) - 1))
            
            # Calculate total pages
            total_pages = len(page_boundaries)
            
            # Ensure page is within valid range
            page = max(0, min(page, total_pages - 1))
            
            # Get the content for the current page
            if total_pages > 0 and page < total_pages:
                page_start, page_end = page_boundaries[page]
                current_page_entries = entry_heights[page_start:page_end + 1]
            else:
                current_page_entries = []
            
            # Print header
            self.console.print(f"[bold cyan]{title} (Page {page + 1}/{total_pages})[/bold cyan]")
            
            # Show range of entries being displayed
            if current_page_entries:
                first_idx = current_page_entries[0][0]
                last_idx = current_page_entries[-1][0]
                total_lines_on_page = sum(height for _, _, height in current_page_entries)
                self.console.print(f"Showing entries {first_idx + 1}-{last_idx + 1} of {len(log_content)} | Terminal: {terminal_height}x{terminal_width}")
            else:
                self.console.print(f"No entries to display | Terminal: {terminal_height}x{terminal_width}")
            
            # Add debug info
            if current_page_entries:
                total_lines_on_page = sum(height for _, _, height in current_page_entries)
                debug_info = f"Page: {page+1}/{total_pages}, Available lines: {max_display_lines}, Used lines: {total_lines_on_page}, Items on page: {len(current_page_entries)}"
            else:
                debug_info = f"Page: {page+1}/{total_pages}, Available lines: {max_display_lines}, No items on page"
            self.console.print(f"[dim]{debug_info}[/dim]")
            
            # Get and display the current heading
            if is_search_result:
                # For search results, we don't have line numbers, so we can't determine the heading
                self.console.print("[dim]Heading not available in search results[/dim]")
            elif current_page_entries:
                current_heading = self.get_current_heading(first_idx)
                if current_heading:
                    heading_text = current_heading['text']
                    self.console.print(f"[bold yellow]CURRENT HEADING: {heading_text}[/bold yellow]")
                else:
                    self.console.print("[dim]No current heading[/dim]")
            else:
                self.console.print("[dim]No current heading[/dim]")
            
            # Calculate the maximum content area height (leave room for navigation at bottom)
            max_content_height = terminal_height - 6  # 4 for header, 2 for navigation
            
            # Display log lines with syntax highlighting based on log level
            lines_displayed = 0
            for idx, line, height in current_page_entries:
                # Stop if we've reached the maximum content height
                if lines_displayed + height > max_content_height:
                    break
                    
                # Handle search results differently
                if is_search_result:
                    # For search results, line is actually a tuple (line, search_term)
                    original_line = log_content[idx][0]
                    search_term = log_content[idx][1]
                else:
                    original_line = line
                
                # Determine style based on log level
                style = None
                if original_line.startswith("DEBUG"):
                    style = "blue"
                elif original_line.startswith("INFO"):
                    style = "green"
                elif original_line.startswith("WARNING"):
                    style = "yellow"
                elif original_line.startswith("ERROR"):
                    style = "red"
                elif original_line.startswith("CRITICAL"):
                    style = "red bold"
                
                # Calculate if we need to truncate the line
                effective_width = terminal_width - 5
                max_chars = effective_width * max_entry_height
                
                # For search results, highlight the search term
                if is_search_result:
                    # Truncate if necessary
                    display_line = original_line
                    if len(display_line) > max_chars:
                        display_line = display_line[:max_chars] + "... [dim](truncated)[/dim]"
                    
                    text = Text(display_line.strip())
                    if style:
                        text.stylize(style)
                    
                    # Find all occurrences of the search term (case insensitive)
                    line_lower = display_line.lower()
                    term_lower = search_term.lower()
                    start = 0
                    while True:
                        pos = line_lower.find(term_lower, start)
                        if pos == -1:
                            break
                        # Add reverse video style to the search term
                        text.stylize("reverse", pos, pos + len(search_term))
                        start = pos + 1
                    
                    self.console.print(text)
                else:
                    # Truncate if necessary
                    display_line = original_line
                    if len(display_line) > max_chars:
                        display_line = display_line[:max_chars] + "... [dim](truncated)[/dim]"
                    
                    # Print normal line with style if set
                    if style:
                        self.console.print(display_line.strip(), style=style)
                    else:
                        self.console.print(display_line.strip())
                
                lines_displayed += height
            
            # Move cursor to the bottom of the terminal for fixed navigation bar
            # Use ANSI escape sequence to position cursor at specific row
            print(f"\033[{terminal_height-2};1H", end="")
            
            # Create navigation text
            nav_text = Text()
            nav_text.append("Navigate: ", style="bold")
            nav_text.append("[n]ext ", style="cyan" if page < total_pages - 1 else "dim")
            nav_text.append("[p]rev ", style="cyan" if page > 0 else "dim")
            nav_text.append("[b]ack ", style="cyan")  # Always show back as available
            nav_text.append("[f]irst ", style="cyan")
            nav_text.append("[l]ast ", style="cyan")
            nav_text.append("[s]earch ", style="cyan")
            nav_text.append("[g]oto heading ", style="cyan")
            nav_text.append("[q]uit", style="red")
            
            # Add page counter with right alignment
            page_counter = f"Page {page + 1}/{total_pages}"
            padding = terminal_width - len(nav_text.plain) - len(page_counter) - 2  # -2 for safety margin
            if padding > 0:
                nav_text.append(" " * padding)
                nav_text.append(page_counter, style="bold")
            
            # Print navigation with dark background
            self.console.print(nav_text, style="on grey11")
            
            # Get user choice
            choice = get_single_key().lower()
            
            if choice == 'q':
                sys.exit(0)
            elif choice == 'b':
                if page > 0:
                    # If not on the first page, go back one page
                    page -= 1
                else:
                    # If on the first page, return to the log list
                    return
            elif choice == 'p' and page > 0:
                page -= 1
            elif choice == 'n' and page < total_pages - 1:
                page += 1
            elif choice == 'f':
                page = 0
            elif choice == 'l':
                page = total_pages - 1
            elif choice == 's':
                # Store current page
                current_page = page
                # Perform search
                self.search_logs()
                # Restore page when returning from search
                page = current_page
            elif choice == 'g':
                # Jump to a specific heading
                page = self.goto_heading()

    def find_last_heading(self):
        """Find and display the last section heading in the log file."""
        if not self.current_log_content:
            self.console.print("[yellow]No log content to search for headings.[/yellow]")
            self.console.print("\nPress any key to continue...")
            get_single_key()
            return
            
        # Clear screen
        os.system('cls' if os.name == 'nt' else 'clear')
        
        # Pattern to identify heading sections (lines with multiple '=' characters)
        separator_pattern = re.compile(r'^=+$')  # One or more '=' characters
        
        # Variables to track the heading
        last_heading = None
        last_heading_line = None
        heading_context = []
        
        # Scan through the log content to find all heading sections
        # We'll keep track of all headings and then display the last one
        headings = []
        i = 0
        while i < len(self.current_log_content):
            line = self.current_log_content[i].strip()
            
            # Check if this is a separator line
            if separator_pattern.match(line):
                # Found a potential start of heading section
                start_line = i
                
                # Look for the heading text and end separator
                if i + 1 < len(self.current_log_content):
                    heading_text = self.current_log_content[i + 1].strip()
                    
                    # Check if there's another separator line after the heading text
                    if i + 2 < len(self.current_log_content) and separator_pattern.match(self.current_log_content[i + 2].strip()):
                        # This is a confirmed heading section
                        # Collect context (lines after the heading section)
                        context = []
                        context_start = i + 3  # Start after the end separator
                        for j in range(context_start, min(context_start + 5, len(self.current_log_content))):
                            if j < len(self.current_log_content):
                                context_line = self.current_log_content[j].strip()
                                if context_line and not separator_pattern.match(context_line):
                                    context.append(context_line)
                        
                        # Add this heading to our list
                        headings.append({
                            'text': heading_text,
                            'line': i + 1,
                            'context': context
                        })
                        
                        # Skip past this heading section
                        i = i + 3
                        continue
            
            i += 1
        
        # Get the last heading if any were found
        if headings:
            last_heading_data = headings[-1]
            last_heading = last_heading_data['text']
            last_heading_line = last_heading_data['line']
            heading_context = last_heading_data['context']
        
        if last_heading:
            # Display the heading with its context
            self.console.print(f"[bold cyan]TAC Log Viewer - Last Section Heading in {os.path.basename(self.current_log_path)}[/bold cyan]\n")
            
            # Create a panel with the heading
            panel = Panel(
                Text(last_heading, style="bold green"),
                title="Section Heading",
                border_style="cyan"
            )
            self.console.print(panel)
            
            # Show the line number
            self.console.print(f"\nFound at line {last_heading_line + 1} in the log file.")
            
            # Show context after the heading
            if heading_context:
                self.console.print("\n[bold]Context after heading:[/bold]")
                for line in heading_context:
                    # Determine style based on log level
                    style = None
                    if line.startswith("DEBUG"):
                        style = "blue"
                    elif line.startswith("INFO"):
                        style = "green"
                    elif line.startswith("WARNING"):
                        style = "yellow"
                    elif line.startswith("ERROR"):
                        style = "red"
                    elif line.startswith("CRITICAL"):
                        style = "red bold"
                    
                    # Print with style if set
                    if style:
                        self.console.print(line, style=style)
                    else:
                        self.console.print(line)
        else:
            self.console.print("[yellow]No section headings found in the log file.[/yellow]")
        
        # Wait for user input before returning
        self.console.print("\nPress any key to return...")
        get_single_key()

    def goto_heading(self):
        """Show a list of headings and jump to the selected one."""
        if not hasattr(self, 'headings') or not self.headings:
            self.console.print("[yellow]No headings found in the log file.[/yellow]")
            self.console.print("\nPress any other key to cancel...")
            get_single_key()
            return 0  # Return to first page
            
        # Clear screen
        os.system('cls' if os.name == 'nt' else 'clear')
        
        # Display all headings
        self.console.print(f"[bold cyan]TAC Log Viewer - Headings in {os.path.basename(self.current_log_path)}[/bold cyan]\n")
        
        for i, heading in enumerate(self.headings, 1):
            # Show full heading text
            heading_text = heading['text']
            self.console.print(f"{i}. {heading_text} (line {heading['line'] + 1})")
        
        # Get user choice
        self.console.print("\nEnter heading number (or press any other key to cancel):")
        choice_str = ""
        while True:
            key = get_single_key()
            if key.isdigit():
                choice_str += key
                self.console.print(key, end="")
            else:
                break
                
        try:
            choice = int(choice_str)
            if 1 <= choice <= len(self.headings):
                # Get the line number for this heading
                heading_line = self.headings[choice - 1]['start_line']
                
                # Get terminal size
                terminal_height = os.get_terminal_size().lines
                terminal_width = os.get_terminal_size().columns
                
                # Calculate available height similar to display_log_content
                available_height = terminal_height - 3 - 2 - 1
                max_display_lines = max(4, min(40, available_height))
                
                # Calculate how many rendered lines each log line will take
                rendered_lines_per_log_line = []
                for line in self.current_log_content:
                    # Calculate how many lines this will take when rendered
                    effective_width = terminal_width - 5
                    line_length = len(line.strip())
                    lines_needed = max(1, (line_length + effective_width - 1) // effective_width)
                    rendered_lines_per_log_line.append(lines_needed)
                
                # Calculate which page contains the heading
                rendered_lines_before_heading = 0
                for i in range(heading_line):
                    rendered_lines_before_heading += rendered_lines_per_log_line[i]
                
                page = rendered_lines_before_heading // max_display_lines
                
                # Show a confirmation message
                self.console.print(f"\n[green]Jumping to heading: {self.headings[choice - 1]['text']}[/green]")
                time.sleep(1)  # Brief pause to show the message
                
                return page
        except ValueError:
            pass
            
        # If we get here, either the choice was invalid or the user cancelled
        return 0  # Return to first page

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='TAC Log Viewer')
    parser.add_argument('--last-heading', action='store_true', help='Show the last heading in the most recent log file')
    args = parser.parse_args()
    
    viewer = TACViewer()
    
    # If --last-heading is specified, show the last heading and exit
    if args.last_heading:
        logs = viewer.list_logs()
        if not logs:
            viewer.console.print("[yellow]No log files found.[/yellow]")
            return
        
        # Use the most recent log file
        viewer.current_log_path = logs[0]
        if viewer.read_log(viewer.current_log_path):
            viewer.find_last_heading()
        return
    
    # Go directly to the logs menu instead of showing the main menu
    viewer.logs_menu()

if __name__ == "__main__":
    main() 
