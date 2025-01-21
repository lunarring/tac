#!/usr/bin/env python
import os
import sys
from rich.console import Console
from tdac.utils.log_manager import LogManager
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from datetime import datetime

class LogViewer:
    def __init__(self):
        self.console = Console()
        self.log_manager = LogManager()
        self.current_log = None
        self.history = []  # Stack to track menu history and their arguments
        
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
            
    def show_menu(self, options: list, title: str = None) -> None:
        """Display a menu with numbered options."""
        if title:
            self.console.print(f"\n[bold cyan]{title}[/bold cyan]")
        self.console.print("\nChoose an option:")
        for i, option in enumerate(options, 1):
            self.console.print(f"{i}. {option}")
        if self.history:  # Show back option only if we have history
            self.console.print("b. Back")
        self.console.print("q. Quit")
        
    def get_choice(self, max_choice: int) -> str:
        """Get user choice with validation."""
        while True:
            choice = input("\nEnter your choice: ").lower()
            if choice == 'q':
                sys.exit(0)
            if choice == 'b' and self.history:
                return 'b'
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
            menu_func(*args)
            
    def main_menu(self) -> None:
        """Show main menu with available log files."""
        while True:
            logs = self.log_manager.list_logs()
            if not logs:
                self.console.print("[yellow]No log files found.[/yellow]")
                input("Press Enter to quit...")
                return
                
            # Create options with human-friendly times
            options = []
            for log in logs:
                mtime = os.path.getmtime(log)
                time_diff = self.get_human_time_diff(mtime)
                options.append(f"{log} ({time_diff})")
                
            self.show_menu(options, "Available Log Files")
            choice = self.get_choice(len(logs))  # Still use original logs length
            
            if choice == 'b':
                self.go_back()
                continue
                
            self.add_to_history(self.main_menu)
            self.log_manager.load_log(logs[choice - 1])  # Use original log name
            self.log_menu()
            
    def log_menu(self) -> None:
        """Show menu for a specific log file."""
        while True:
            options = [
                "Show overview (tree view)",
                "View configuration",
                f"View executions (1-{self.log_manager.get_execution_count()})"
            ]
            
            self.show_menu(options, f"Log File: {self.log_manager.current_log_path}")
            choice = self.get_choice(len(options))
            
            if choice == 'b':
                self.go_back()
                return
                
            self.add_to_history(self.log_menu)
            
            if choice == 1:
                self.log_manager.display_log_tree()
                input("\nPress Enter to continue...")
            elif choice == 2:
                self.log_manager.display_config()
                input("\nPress Enter to continue...")
            elif choice == 3:
                self.execution_menu()
                
    def execution_menu(self) -> None:
        """Show menu for viewing executions."""
        while True:
            exec_count = self.log_manager.get_execution_count()
            options = [f"Execution {i}" for i in range(1, exec_count + 1)]
            
            self.show_menu(options, "Available Executions")
            choice = self.get_choice(len(options))
            
            if choice == 'b':
                self.go_back()
                return
                
            self.add_to_history(self.execution_menu)
            self.execution_details_menu(choice)
            
    def execution_details_menu(self, execution_num: int) -> None:
        """Show menu for specific execution components."""
        while True:
            options = [
                "Basic info (timestamp, success, attempt)",
                "Protoblock details",
                "Git diff",
                "Test results"
            ]
            
            self.show_menu(options, f"Execution {execution_num} Components")
            choice = self.get_choice(len(options))
            
            if choice == 'b':
                self.go_back()
                return
                
            self.add_to_history(self.execution_details_menu, execution_num)
            
            try:
                execution = self.log_manager.current_log['executions'][execution_num - 1]
                
                if choice == 1:
                    # Show basic info
                    table = Table(title=f"Execution {execution_num} Basic Info")
                    table.add_column("Field", style="cyan")
                    table.add_column("Value", style="green")
                    table.add_row("Timestamp", execution['timestamp'])
                    table.add_row("Success", "✅" if execution['success'] else "❌")
                    table.add_row("Attempt", str(execution['attempt']))
                    self.console.print(table)
                    
                elif choice == 2:
                    # Show protoblock details
                    proto_text = Text()
                    for key, value in execution['protoblock'].items():
                        proto_text.append(f"{key}: ", style="cyan")
                        proto_text.append(f"{value}\n", style="green")
                    self.console.print(Panel(proto_text, title="Protoblock Details"))
                    
                elif choice == 3:
                    # Show git diff
                    if execution['git_diff'].strip():
                        self.console.print(Panel(execution['git_diff'], title="Git Diff"))
                    else:
                        self.console.print("[yellow]No git diff available[/yellow]")
                        
                elif choice == 4:
                    # Show test results
                    if execution['test_results'].strip():
                        self.console.print(Panel(execution['test_results'], title="Test Results"))
                    else:
                        self.console.print("[yellow]No test results available[/yellow]")
                        
                input("\nPress Enter to continue...")
            except IndexError:
                self.console.print("[red]Invalid execution number. Please try again.[/red]")

def main():
    try:
        viewer = LogViewer()
        viewer.main_menu()
    except KeyboardInterrupt:
        print("\nGoodbye!")
        sys.exit(0)

if __name__ == "__main__":
    main() 