#!/usr/bin/env python
import os
import sys
from rich.console import Console
from tac.utils.log_manager import LogManager
from rich.panel import Panel
from rich.text import Text
from datetime import datetime
import re

class TACViewer:
    def __init__(self):
        self.console = Console()
        self.log_manager = LogManager()
        self.history = []  # Stack to track menu history and their arguments
        self.items_per_page = 10  # Number of items to show per page
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
        """Get user choice with validation."""
        while True:
            choice = input("\nEnter your choice: ").lower()
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
                
    def logs_menu(self) -> None:
        """Show menu with available log files."""
        page = 0  # Start at first page
        while True:
            logs = self.log_manager.list_logs()
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
                self.add_to_history(self.logs_menu)
                self.current_log_path = current_logs[choice - 1]
                self.current_log_content = self.log_manager.read_log(self.current_log_path)
                self.log_menu()
    
    def log_menu(self) -> None:
        """Show menu for a specific log file."""
        while True:
            options = [
                "View entire log",
                "View DEBUG logs only",
                "View INFO logs only",
                "View WARNING logs only",
                "View ERROR logs only",
                "Search logs"
            ]
            
            log_name = os.path.basename(self.current_log_path)
            self.show_menu(options, f"Log File: {log_name}")
            choice = self.get_choice(len(options))
            
            if choice == 'b':
                if self.go_back():
                    break
                continue
                
            self.add_to_history(self.log_menu)
            
            if choice == 1:  # View entire log
                self.display_log_content(self.current_log_content)
            elif choice == 2:  # DEBUG logs
                self.display_filtered_logs("DEBUG")
            elif choice == 3:  # INFO logs
                self.display_filtered_logs("INFO")
            elif choice == 4:  # WARNING logs
                self.display_filtered_logs("WARNING")
            elif choice == 5:  # ERROR logs
                self.display_filtered_logs("ERROR")
            elif choice == 6:  # Search logs
                self.search_logs()
    
    def display_log_content(self, log_content, title="Log Contents"):
        """Display log content in a paged view."""
        page = 0
        lines_per_page = 20
        
        while True:
            start_idx = page * lines_per_page
            end_idx = start_idx + lines_per_page
            current_lines = log_content[start_idx:end_idx]
            
            if not current_lines:
                self.console.print("[yellow]No log entries to display.[/yellow]")
                input("Press Enter to continue...")
                return
                
            total_pages = (len(log_content) + lines_per_page - 1) // lines_per_page
            
            self.console.print(f"\n[bold cyan]{title} (Page {page + 1}/{total_pages})[/bold cyan]")
            
            # Display log lines with syntax highlighting based on log level
            for line in current_lines:
                if line.startswith("DEBUG"):
                    self.console.print(line.strip(), style="blue")
                elif line.startswith("INFO"):
                    self.console.print(line.strip(), style="green")
                elif line.startswith("WARNING"):
                    self.console.print(line.strip(), style="yellow")
                elif line.startswith("ERROR") or line.startswith("CRITICAL"):
                    self.console.print(line.strip(), style="red")
                else:
                    self.console.print(line.strip())
            
            # Navigation options
            self.console.print("\nNavigation:")
            if page > 0:
                self.console.print("p. Previous page")
            if end_idx < len(log_content):
                self.console.print("n. Next page")
            self.console.print("b. Back")
            self.console.print("q. Quit")
            
            choice = input("\nEnter your choice: ").lower()
            
            if choice == 'q':
                sys.exit(0)
            elif choice == 'b':
                return
            elif choice == 'p' and page > 0:
                page -= 1
            elif choice == 'n' and end_idx < len(log_content):
                page += 1
    
    def display_filtered_logs(self, level):
        """Display logs filtered by level."""
        filtered_logs = [line for line in self.current_log_content if line.startswith(level)]
        self.display_log_content(filtered_logs, f"{level} Log Entries")
    
    def search_logs(self):
        """Search logs for a specific term."""
        search_term = input("\nEnter search term: ")
        if not search_term:
            return
            
        # Case-insensitive search
        pattern = re.compile(search_term, re.IGNORECASE)
        matching_logs = [line for line in self.current_log_content if pattern.search(line)]
        
        self.display_log_content(matching_logs, f"Search Results for '{search_term}'")

def main():
    """Main entry point for the TAC viewer."""
    viewer = TACViewer()
    viewer.main_menu()

if __name__ == "__main__":
    main() 
