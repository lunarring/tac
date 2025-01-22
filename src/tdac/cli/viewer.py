#!/usr/bin/env python
import os
import sys
import json
from rich.console import Console
from tdac.utils.log_manager import LogManager
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from datetime import datetime

class TDACViewer:
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
        """Show main menu to choose between logs and protoblocks."""
        while True:
            options = ["View Logs", "View Protoblocks"]
            self.show_menu(options, "TDAC Viewer")
            choice = self.get_choice(len(options))
            
            if choice == 'b':
                self.go_back()
                continue
                
            self.add_to_history(self.main_menu)
            if choice == 1:
                self.logs_menu()
            else:
                self.protoblocks_menu()
                
    def logs_menu(self) -> None:
        """Show menu with available log files."""
        while True:
            logs = self.log_manager.list_logs()
            if not logs:
                self.console.print("[yellow]No log files found.[/yellow]")
                input("Press Enter to continue...")
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
                
            self.add_to_history(self.logs_menu)
            self.log_manager.load_log(logs[choice - 1])  # Use original log name
            self.log_menu()
            
    def protoblocks_menu(self) -> None:
        """Show menu with available protoblock files."""
        while True:
            protoblocks = [f for f in os.listdir('.') if f.startswith('.tdac_protoblock_') and f.endswith('.json')]
            if not protoblocks:
                self.console.print("[yellow]No protoblock files found.[/yellow]")
                input("Press Enter to continue...")
                return
                
            # Sort protoblocks by modification time (newest first)
            protoblocks.sort(key=lambda x: os.path.getmtime(x), reverse=True)
                
            # Create options with human-friendly times and template type
            options = []
            for pb in protoblocks:
                mtime = os.path.getmtime(pb)
                time_diff = self.get_human_time_diff(mtime)
                try:
                    with open(pb, 'r') as f:
                        data = json.load(f)
                    template_type = data.get('template_type', 'unknown')
                    options.append(f"{pb} ({template_type}, {time_diff})")
                except:
                    options.append(f"{pb} (error reading file, {time_diff})")
                
            self.show_menu(options, "Available Protoblocks")
            choice = self.get_choice(len(protoblocks))
            
            if choice == 'b':
                self.go_back()
                continue
                
            self.add_to_history(self.protoblocks_menu)
            self.protoblock_menu(protoblocks[choice - 1])
            
    def protoblock_menu(self, protoblock_file: str) -> None:
        """Show menu for a specific protoblock file."""
        try:
            with open(protoblock_file, 'r') as f:
                data = json.load(f)
        except Exception as e:
            self.console.print(f"[red]Error reading protoblock file: {e}[/red]")
            input("\nPress Enter to continue...")
            return
            
        while True:
            versions = data.get('versions', [data])  # Use data itself as single version for legacy format
            options = []
            
            # Add version options
            for i, version in enumerate(versions, 1):
                timestamp = version.get('timestamp', 'N/A')
                if timestamp != 'N/A':
                    try:
                        dt = datetime.fromisoformat(timestamp)
                        timestamp = self.get_human_time_diff(dt.timestamp())
                    except:
                        pass
                options.append(f"View version {i} ({timestamp})")
                
            # Add basic info as last option
            options.append("Show basic info")
            
            self.show_menu(options, f"Protoblock File: {protoblock_file}")
            choice = self.get_choice(len(options))
            
            if choice == 'b':
                self.go_back()
                return
                
            self.add_to_history(self.protoblock_menu, protoblock_file)
            
            if choice == len(options):  # Last option is basic info
                # Show basic info
                table = Table(title=f"Protoblock Basic Info")
                table.add_column("Field", style="cyan")
                table.add_column("Value", style="green")
                table.add_row("Block ID", data.get('block_id', 'N/A'))
                table.add_row("Template Type", data.get('template_type', 'N/A'))
                table.add_row("Version Count", str(len(versions)))
                self.console.print(table)
                input("\nPress Enter to continue...")
            else:  # Version options
                self.display_protoblock_version(versions[choice - 1])
                input("\nPress Enter to continue...")
                
    def display_protoblock_version(self, version: dict) -> None:
        """Display all components of a protoblock version at once."""
        try:
            # Show task specification
            self.console.print("\n[bold cyan]Task Specification[/bold cyan]")
            self.console.print(Panel(version['task']['specification']))
            
            # Show test specification
            self.console.print("\n[bold cyan]Test Specification[/bold cyan]")
            self.console.print(Panel(version['test']['specification']))
            
            # Show test data
            self.console.print("\n[bold cyan]Test Data[/bold cyan]")
            self.console.print(Panel(version['test']['data']))
            
            # Show files to write
            self.console.print("\n[bold cyan]Files to Write[/bold cyan]")
            files = version.get('write_files', [])
            if files:
                self.console.print(Panel("\n".join(files)))
            else:
                self.console.print("[yellow]No files to write specified[/yellow]")
                
            # Show context files
            self.console.print("\n[bold cyan]Context Files[/bold cyan]")
            files = version.get('context_files', [])
            if files:
                self.console.print(Panel("\n".join(files)))
            else:
                self.console.print("[yellow]No context files specified[/yellow]")
                
            # Show commit message
            self.console.print("\n[bold cyan]Commit Message[/bold cyan]")
            msg = version.get('commit_message', 'N/A')
            self.console.print(Panel(msg))
            
        except Exception as e:
            self.console.print(f"[red]Error displaying protoblock content: {e}[/red]")
                
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
                "Test results",
                "Failure analysis"
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
                        
                elif choice == 5:
                    # Show failure analysis
                    if 'failure_analysis' in execution and execution['failure_analysis'].strip():
                        self.console.print(Panel(execution['failure_analysis'], title="Failure Analysis", style="red"))
                    else:
                        self.console.print("[yellow]No failure analysis available (execution may have succeeded)[/yellow]")
                        
                input("\nPress Enter to continue...")
            except IndexError:
                self.console.print("[red]Invalid execution number. Please try again.[/red]")

def main():
    try:
        viewer = TDACViewer()
        viewer.main_menu()
    except KeyboardInterrupt:
        print("\nGoodbye!")
        sys.exit(0)

if __name__ == "__main__":
    main() 