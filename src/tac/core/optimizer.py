import os
import ast
import logging
from typing import Tuple, Optional

from tac.core.block_runner import BlockRunner
from tac.utils.project_files import ProjectFiles

logger = logging.getLogger(__name__)

class CodeOptimizer:
    """Class responsible for optimizing Python code functions."""
    
    def __init__(self):
        self.project_files = ProjectFiles()
        self.project_files.update_summaries()
        self.codebase = self.project_files.get_codebase_summary()
    
    def find_function(self, function_name: str) -> Tuple[bool, Optional[str]]:
        """
        Find a function in the codebase by name.
        
        Args:
            function_name: Name of the function to find
            
        Returns:
            Tuple of (found: bool, file_path: Optional[str])
        """
        for root, _, files in os.walk('.'):
            for file in files:
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            tree = ast.parse(f.read(), filename=file_path)
                            for node in ast.walk(tree):
                                if isinstance(node, ast.FunctionDef) and node.name == function_name:
                                    return True, file_path
                    except Exception as e:
                        logger.debug(f"Error parsing {file_path}: {e}")
                        continue
        return False, None

