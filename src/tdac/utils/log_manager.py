import os
import json
from typing import Dict, List, Any, Optional
from datetime import datetime
from rich.tree import Tree
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

class LogManager:
    """
    A class to manage and navigate TDAC log files in an interactive way.
    Provides tree-like navigation and rich display of log contents.
    """
    
    def __init__(self):
        self.console = Console()
        self.current_log: Optional[Dict] = None
        self.current_log_path: Optional[str] = None
        
    def list_logs(self) -> List[str]:
        """List all available log files in the current directory."""
        return sorted(
            [f for f in os.listdir('.') if f.startswith('.tdac_log_')],
            key=lambda x: os.path.getmtime(x),
            reverse=True
        )
        
    def load_log(self, log_path: str) -> bool:
        """Load a specific log file into memory."""
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                self.current_log = json.load(f)
            self.current_log_path = log_path
            return True
        except Exception as e:
            self.console.print(f"[red]Error loading log file: {e}[/red]")
            return False
            
    def display_log_tree(self) -> None:
        """Display the current log file as a navigable tree structure."""
        if not self.current_log:
            self.console.print("[yellow]No log file loaded. Use load_log() first.[/yellow]")
            return
            
        tree = Tree(f"📋 Log File: {self.current_log_path}")
        
        # Add config branch
        config_branch = tree.add("⚙️ Config")
        self._add_dict_to_tree(self.current_log['config'], config_branch)
        
        # Add executions branch
        executions_branch = tree.add(f"🔄 Executions ({len(self.current_log['executions'])})")
        for i, execution in enumerate(self.current_log['executions'], 1):
            exec_branch = executions_branch.add(
                f"Execution {i} - {'✅' if execution['success'] else '❌'} ({execution['timestamp']})"
            )
            self._add_execution_to_tree(execution, exec_branch)
        
        self.console.print(tree)
        
    def _add_dict_to_tree(self, data: Dict, parent: Tree, max_str_length: int = 100) -> None:
        """Recursively add dictionary contents to tree."""
        for key, value in data.items():
            if isinstance(value, dict):
                branch = parent.add(f"📁 {key}")
                self._add_dict_to_tree(value, branch)
            elif isinstance(value, list):
                branch = parent.add(f"📋 {key} ({len(value)} items)")
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        item_branch = branch.add(f"Item {i+1}")
                        self._add_dict_to_tree(item, item_branch)
                    else:
                        branch.add(str(item)[:max_str_length])
            else:
                str_value = str(value)
                if len(str_value) > max_str_length:
                    str_value = str_value[:max_str_length] + "..."
                parent.add(f"{key}: {str_value}")
                
    def _add_execution_to_tree(self, execution: Dict, parent: Tree) -> None:
        """Add execution details to tree."""
        # Add protoblock info
        proto_branch = parent.add("📝 Protoblock")
        self._add_dict_to_tree(execution['protoblock'], proto_branch)
        
        # Add git diff (truncated)
        if execution['git_diff'].strip():
            diff_preview = execution['git_diff'][:100] + "..." if len(execution['git_diff']) > 100 else execution['git_diff']
            parent.add(f"📊 Git Diff: {diff_preview}")
            
        # Add test results (truncated)
        if execution['test_results'].strip():
            test_preview = execution['test_results'][:100] + "..." if len(execution['test_results']) > 100 else execution['test_results']
            parent.add(f"🧪 Test Results: {test_preview}")
            
    def display_execution_details(self, execution_index: int) -> None:
        """Display full details of a specific execution."""
        if not self.current_log:
            self.console.print("[yellow]No log file loaded. Use load_log() first.[/yellow]")
            return
            
        try:
            execution = self.current_log['executions'][execution_index - 1]  # Convert to 0-based index
        except IndexError:
            self.console.print(f"[red]Execution {execution_index} not found.[/red]")
            return
            
        # Create a table for execution details
        table = Table(title=f"Execution {execution_index} Details")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="green")
        
        # Add basic info
        table.add_row("Timestamp", execution['timestamp'])
        table.add_row("Success", "✅" if execution['success'] else "❌")
        table.add_row("Attempt", str(execution['attempt']))
        
        self.console.print(table)
        
        # Show protoblock details in a panel
        proto_text = Text()
        for key, value in execution['protoblock'].items():
            proto_text.append(f"{key}: ", style="cyan")
            proto_text.append(f"{value}\n", style="green")
        self.console.print(Panel(proto_text, title="Protoblock Details"))
        
        # Show git diff in a panel if not empty
        if execution['git_diff'].strip():
            self.console.print(Panel(execution['git_diff'], title="Git Diff"))
            
        # Show test results in a panel if not empty
        if execution['test_results'].strip():
            self.console.print(Panel(execution['test_results'], title="Test Results"))
            
    def display_config(self) -> None:
        """Display the full configuration."""
        if not self.current_log:
            self.console.print("[yellow]No log file loaded. Use load_log() first.[/yellow]")
            return
            
        self.console.print(Panel(
            Text(json.dumps(self.current_log['config'], indent=2)),
            title="Configuration"
        ))
        
    def get_execution_count(self) -> int:
        """Get the number of executions in the current log."""
        if not self.current_log:
            return 0
        return len(self.current_log['executions']) 