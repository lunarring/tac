import os
import ast
from datetime import datetime
from typing import Dict, List, Optional
from tac.core.llm import LLMClient, Message
import logging

logger = logging.getLogger(__name__)

class FileSummarizer:
    """Class for summarizing Python files using LLM analysis"""
    
    def __init__(self):
        self.llm_client = LLMClient()
        # Load config for timeout
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'config.yaml')
        with open(config_path, 'r') as f:
            import yaml
            config = yaml.safe_load(f)
        self.timeout = config.get('general', {}).get('summarizer_timeout', 30)

    def _generate_detailed_summary(self, code: str, functions: list, classes: list) -> str:
        """Generate a detailed analysis of the code by merging summarization responsibilities."""
        prompt = "Analyze the following Python code in detail.\n"
        if functions:
            prompt += "Functions:\n" + "\n".join([f"- {f}" for f in functions]) + "\n"
        if classes:
            prompt += "Classes and their methods:\n"
            for cls in classes:
                methods = ", ".join(cls.get("methods", []))
                prompt += f"- {cls['name']}: {methods}\n"
        prompt += f"\nFull Code:\n<code>\n{code}\n</code>\n"
        prompt += "Please provide a detailed technical analysis including inner workings, purpose, dependencies, and input output expectations of each component. The output format should be a text beginning with the function/class name and then your analysis. Then in the next line, continue. Add no other formatting elements!"
        
        try:
            messages = [
                Message(role="system", content="You are a Python code analysis expert. Provide clear, detailed technical summaries of code structures."),
                Message(role="user", content=prompt)
            ]
            
            import signal
            from contextlib import contextmanager
            
            @contextmanager
            def timeout(seconds):
                def signal_handler(signum, frame):
                    raise TimeoutError(f"LLM call timed out after {seconds} seconds")
                signal.signal(signal.SIGALRM, signal_handler)
                signal.alarm(seconds)
                try:
                    yield
                finally:
                    signal.alarm(0)
            
            with timeout(self.timeout):
                return self.llm_client.chat_completion(messages)
        except TimeoutError as e:
            logger.error(str(e))
            return f"Error: {str(e)}"
        except Exception as e:
            logger.error(f"LLM call failed: {str(e)}")
            return f"Error: LLM call failed - {str(e)}"

    def _extract_code_block(self, node: ast.AST) -> str:
        """Extract the source code for a given AST node"""
        if hasattr(node, 'lineno') and hasattr(node, 'end_lineno'):
            lines = self.current_file_content.splitlines()
            return '\n'.join(lines[node.lineno - 1:node.end_lineno])
        return ""

    def _analyze_file(self, file_path: str) -> Dict:
        """Analyze a single Python file and return its summary"""
        try:
            with open(file_path, 'r') as f:
                self.current_file_content = f.read()

            try:
                tree = ast.parse(self.current_file_content)
            except SyntaxError:
                return {
                    "error": "Could not parse file due to syntax error",
                    "content": None
                }

            # Get all functions and classes at once
            functions = []
            classes = []
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.FunctionDef):
                    functions.append(node.name)
                elif isinstance(node, ast.ClassDef):
                    class_info = {"name": node.name, "methods": []}
                    for child in ast.iter_child_nodes(node):
                        if isinstance(child, ast.FunctionDef):
                            class_info["methods"].append(child.name)
                    classes.append(class_info)

            # If no functions or classes found, return early
            if not functions and not classes:
                return {
                    "error": None,
                    "content": []  # Empty content is valid for files with no functions/classes
                }

            summary = self._generate_detailed_summary(self.current_file_content, functions, classes)
            if summary.startswith("Error:"):
                return {
                    "error": summary,
                    "content": None
                }
            return {
                    "error": None,
                    "content": summary
                }
            
        except Exception as e:
            logger.error(f"Error analyzing file {file_path}: {str(e)}")
            return {
                "error": f"Unexpected error: {str(e)}",
                "content": None
            }

    def summarize_directory(self, directory: str, exclusions: Optional[List[str]] = None, exclude_dot_files: bool = True, for_protoblock: bool = False) -> str:
        """
        Summarize all Python files in a directory and its subdirectories.
        
        Args:
            directory: Path to the directory to analyze
            exclusions: List of directory names to exclude
            exclude_dot_files: Whether to exclude files/dirs starting with '.'
            for_protoblock: If True, returns only summaries without metadata
            
        Returns:
            A formatted string containing the directory tree and file summaries
        """
        if exclusions is None:
            exclusions = [".git", "__pycache__", "build"]

        # Size thresholds in bytes (100KB total)
        MAX_FILE_SIZE = 100 * 1024

        directory_tree = []
        file_summaries = []
        seen_files = set()  # Track unique files by their absolute path

        directory = str(directory)  # Ensure directory is a string
        abs_directory = os.path.abspath(directory)  # Get absolute path of base directory

        for root, dirs, files in os.walk(directory):
            # Exclude specified directories and optionally dot directories
            dirs[:] = [d for d in dirs if d not in exclusions and not (exclude_dot_files and d.startswith('.'))]

            # Build directory tree if not for protoblock
            if not for_protoblock:
                level = root.replace(directory, '').count(os.sep)
                indent = ' ' * 4 * level
                directory_tree.append(f"{indent}{os.path.basename(root)}/")

            for file in files:
                if (file.endswith('.py') and 
                    not file.startswith('.#') and  # Skip temp files
                    not (exclude_dot_files and file.startswith('.'))):
                    
                    file_path = os.path.join(root, file)
                    abs_file_path = os.path.abspath(file_path)
                    real_path = os.path.realpath(abs_file_path)  # Resolve any symlinks
                    
                    # Skip if we've seen this file before (either directly or through symlink)
                    if real_path in seen_files:
                        continue
                    
                    # Skip if file is outside the target directory
                    if not real_path.startswith(abs_directory):
                        continue
                    
                    seen_files.add(real_path)
                    if not for_protoblock:
                        directory_tree.append(f"{indent}    {file}")

                    # Skip large files
                    file_size = os.path.getsize(file_path)
                    if file_size > MAX_FILE_SIZE:
                        if not for_protoblock:
                            file_summaries.append(
                                f"## File: {os.path.relpath(file_path, directory)}\n"
                                f"Size: {file_size} bytes (too large to analyze), "
                                f"Last Modified: {datetime.fromtimestamp(os.path.getmtime(file_path))}"
                            )
                        continue

                    # Analyze file
                    file_info = "" if for_protoblock else f"Size: {file_size} bytes, Last Modified: {datetime.fromtimestamp(os.path.getmtime(file_path))}"
                    analysis = self._analyze_file(file_path)

                    if analysis["error"]:
                        summary = f"Error analyzing file: {analysis['error']}"
                    else:
                        if isinstance(analysis["content"], list):
                            # Format summaries from structured data
                            summary_parts = []
                            for item in analysis["content"]:
                                if item["type"] == "function":
                                    summary_parts.append(item["summary"])
                                else:  # class
                                    class_summary = item["summary"]
                                    method_summaries = []
                                    for method in item["methods"]:
                                        method_summary = method["summary"].replace('\n', '\n  ')
                                        method_summaries.append(method_summary)
                                    if method_summaries:
                                        class_summary += "\n\n" + "\n\n".join(method_summaries)
                                    summary_parts.append(class_summary)
                            summary = "\n\n".join(summary_parts)
                        else:
                            # Using flat string summary returned by the LLM client
                            summary = analysis["content"]

                    if for_protoblock:
                        file_summaries.append(f"File: {os.path.relpath(file_path, directory)}\n{summary}")
                    else:
                        file_summaries.append(f"## File: {os.path.relpath(file_path, directory)}\n{file_info}\n\n```python\n{summary}\n```")

        if not file_summaries:
            return "No Python files found."

        if for_protoblock:
            return "\n\n---\n\n".join(file_summaries)
        return "\n".join(directory_tree) + "\n\n---\n\n" + "\n\n---\n\n".join(file_summaries) 
