import os
import json
from typing import Dict, List, Any, Optional
from datetime import datetime
from rich.tree import Tree
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
import logging

logger = logging.getLogger(__name__)

class LogManager:
    """
    A class to manage and navigate TAC log files in an interactive way.
    Provides tree-like navigation and rich display of log contents.
    """
    
    def __init__(self):
        self.console = Console()
        self.current_log: Optional[Dict] = None
        self.current_log_path: Optional[str] = None
        
    def list_logs(self) -> List[str]:
        """List all available log files in the current directory."""
        return sorted(
            [f for f in os.listdir('.') if f.startswith('.tac_log_')],
            key=lambda x: os.path.getmtime(x),
            reverse=True
        )
        
    def load_log(self, log_path: str) -> bool:
        """Load a specific log file into memory."""
        try:
            if os.path.exists(log_path):
                with open(log_path, 'r', encoding='utf-8') as f:
                    self.current_log = json.load(f)
            else:
                # Initialize new log structure if file doesn't exist
                self.current_log = {
                    'config': {},
                    'executions': []
                }
            self.current_log_path = log_path
            return True
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error loading log file {log_path}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error loading log file {log_path}: {str(e)}")
            return False

    def safe_update_log(self, execution_data: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> bool:
        """
        Safely update the log file with new execution data and optionally update config.
        
        Args:
            execution_data: Dictionary containing execution data to append
            config: Optional dictionary containing config data to update
            
        Returns:
            bool: True if update was successful, False otherwise
        """
        if not self.current_log_path:
            logger.error("No log file path set - make sure to set current_log_path before calling safe_update_log")
            return False

        try:
            # Check if directory is writable
            log_dir = os.path.dirname(os.path.abspath(self.current_log_path)) or '.'
            if not os.access(log_dir, os.W_OK):
                logger.error(f"Directory {log_dir} is not writable")
                return False

            # Load current log data or initialize new structure
            if not self.load_log(self.current_log_path):
                logger.error(f"Failed to load or initialize log file at {self.current_log_path}")
                return False

            # Update config if provided
            if config is not None:
                self.current_log['config'] = config

            # Ensure executions list exists
            if 'executions' not in self.current_log:
                self.current_log['executions'] = []

            # Validate execution data
            if not isinstance(execution_data, dict):
                logger.error(f"Invalid execution data type: expected dict, got {type(execution_data)}")
                return False

            # Append new execution data
            self.current_log['executions'].append(execution_data)

            # Write updated log with temporary file approach for safety
            temp_path = f"{self.current_log_path}.tmp"
            try:
                with open(temp_path, 'w', encoding='utf-8') as f:
                    json.dump(self.current_log, f, indent=2, default=str)
                
                # If successful, replace the original file
                os.replace(temp_path, self.current_log_path)
                logger.debug(f"Successfully updated log file at {self.current_log_path}")
                return True
            except Exception as e:
                logger.error(f"Error writing log file {self.current_log_path}: {str(e)}")
                # Clean up temp file if it exists
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except Exception as cleanup_error:
                        logger.warning(f"Failed to clean up temporary file {temp_path}: {cleanup_error}")
                return False

        except Exception as e:
            logger.error(f"Unexpected error updating log {self.current_log_path}: {str(e)}")
            return False

    def get_latest_execution(self) -> Optional[Dict[str, Any]]:
        """Get the most recent execution entry from the log."""
        if not self.current_log or 'executions' not in self.current_log or not self.current_log['executions']:
            return None
        return self.current_log['executions'][-1]

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
        # Add status message if present
        if 'message' in execution and execution['message']:
            parent.add(f"📢 Status: {execution['message']}")
            
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
            
        # Add failure analysis if present
        if 'failure_analysis' in execution and execution['failure_analysis'].strip():
            analysis_preview = execution['failure_analysis'][:100] + "..." if len(execution['failure_analysis']) > 100 else execution['failure_analysis']
            parent.add(f"🔍 Failure Analysis: {analysis_preview}")
        
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
        table.add_row("Success", "✅" if execution['success'] else "❌" if execution['success'] is False else "🔄")
        table.add_row("Attempt", str(execution['attempt']))
        if 'message' in execution:
            table.add_row("Status", execution['message'])
        
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
            
        # Show failure analysis in a panel if present
        if 'failure_analysis' in execution and execution['failure_analysis'].strip():
            self.console.print(Panel(execution['failure_analysis'], title="Failure Analysis", style="red"))
            
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
        """Get the number of unique attempts in the current log."""
        if not self.current_log:
            return 0
        # Get unique attempt numbers
        attempts = {execution['attempt'] for execution in self.current_log['executions']}
        return len(attempts) 