import os
import ast
from datetime import datetime
from typing import Dict, List, Optional
from tac.core.llm import LLMClient, Message
from tac.core.config import config
import logging
from tac.core.log_config import setup_logging
logger = setup_logging('tac.utils.file_summarizer')

class FileSummarizer:
    """Class for summarizing Python files using LLM analysis"""
    
    def __init__(self):
        self.llm_client = LLMClient()
        self.timeout = config.general.summarizer_timeout

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
        prompt += """You are a senior software engineer. Provide a concise analysis of the code's functions and classes. Format your response as follows:
In the beginning, a high-level summary of the entire file
Then for each function/class, start a new line with the exact name of the function/class, followed by a colon and the description.
Keep descriptions technical and focus on functionality and interactions, particularly tell which methods or functions call which other ones and how they are used together. You are using strict formatting. Here is an example of the output format:
Here is a an example of the output format. Don't use any other formatting.
High-level summary: (insert high level summary here, say what this file contains, e.g. if there are classes, functions, tests, etc.)
Function/Class 1 (line begin:line end): (insert description here, with above guidelines in mind)
Function/Class 2 (line begin:line end): (insert description here, with above guidelines in mind)

IMPORTANT: Make sure to include ALL classes and functions in your analysis, not just the first few. The file may contain multiple classes and functions that all need to be described.
"""
        
        messages = [
            Message(role="system", content="You are a Python code analysis expert. Provide clear, detailed technical summaries of code structures. Make sure to analyze ALL classes and functions in the code, not just the first few."),
            Message(role="user", content=prompt)
        ]

        response = self.llm_client.chat_completion(messages)
        
        # Create a mapping of names to their line numbers
        name_to_lines = {}
        for func in functions:
            # Extract name and line numbers from the format "name (lines start-end)"
            name = func.split(" (lines ")[0]
            start, end = func.split(" (lines ")[1].rstrip(")").split("-")
            name_to_lines[name] = (start, end)
        
        for cls in classes:
            name = cls["name"].split(" (lines ")[0]
            start, end = cls["name"].split(" (lines ")[1].rstrip(")").split("-")
            name_to_lines[name] = (start, end)

        # Split response into lines
        lines = response.strip().split("\n")
        if not lines:
            return response

        # Keep the first line (high-level summary) as is
        formatted_lines = [lines[0]]
        
        # Process remaining lines
        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue
                
            # Find the first colon which separates name from description
            parts = line.split(":", 1)
            if len(parts) != 2:
                formatted_lines.append(line)  # Keep unchanged if no colon found
                continue
                
            name = parts[0].strip()
            description = parts[1].strip()
            
            # Find the matching name in our definitions
            for def_name, (start, end) in name_to_lines.items():
                if def_name in name:  # Using 'in' to match even if LLM added some prefix
                    formatted_line = f"{def_name} (line {start}:{end}): {description}"
                    formatted_lines.append(formatted_line)
                    break
            else:
                # If no match found, keep the line unchanged
                formatted_lines.append(line)
        
        return "\n".join(formatted_lines)


    def analyze_file(self, file_path: str) -> Dict:
        """Analyze a single Python file and return its summary"""
        try:
            with open(file_path, 'r') as f:
                self.current_file_content = f.read()

            # Use extract_code_definitions to get functions and classes with line numbers
            definitions = extract_code_definitions(self.current_file_content)

            # If no functions or classes found, return early
            if not definitions:
                return {
                    "error": None,
                    "content": []  # Empty content is valid for files with no functions/classes
                }

            functions = []
            classes = []
            methods_by_class = {}
            
            # First pass: collect classes and functions
            for defn in definitions:
                if defn['type'] == 'function':
                    functions.append(f"{defn['name']} (lines {defn['start_line']}-{defn['end_line']})")
                elif defn['type'] == 'class':
                    classes.append({
                        "name": f"{defn['name']} (lines {defn['start_line']}-{defn['end_line']})",
                        "methods": []
                    })
                    methods_by_class[defn['name']] = []
                elif defn['type'] == 'method':
                    class_name = defn['name'].split('.')[0]  # Get the first part before the dot
                    method_str = f"{defn['name']} (lines {defn['start_line']}-{defn['end_line']})"
                    if class_name in methods_by_class:
                        methods_by_class[class_name].append(method_str)
            
            # Second pass: add methods to their classes
            for cls in classes:
                class_name = cls["name"].split(" (lines ")[0]
                if class_name in methods_by_class:
                    cls["methods"] = methods_by_class[class_name]
                    # Also add methods to functions list so they get their own descriptions
                    functions.extend(methods_by_class[class_name])

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


def extract_code_definitions(code: str):
    """
    Extracts all function and class definitions from Python code along with their starting and ending line numbers.
    
    Args:
        code (str): Python source code.
        
    Returns:
        list of dict: A list of dictionaries each containing:
            - 'type': 'function' or 'class'
            - 'name': Name of the function or class
            - 'start_line': The starting line number of the definition
            - 'end_line': The ending line number of the definition
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    
    definitions = []
    
    # Helper function to recursively process nodes
    def process_node(node, parent_name=None):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = node.name
            if parent_name:
                name = f"{parent_name}.{name}"
                node_type = 'method'
            else:
                node_type = 'function'
                
            definitions.append({
                'type': node_type,
                'name': name,
                'start_line': node.lineno,
                'end_line': getattr(node, "end_lineno", node.lineno)
            })
            
        elif isinstance(node, ast.ClassDef):
            name = node.name
            if parent_name:
                name = f"{parent_name}.{name}"
                
            class_def = {
                'type': 'class',
                'name': name,
                'start_line': node.lineno,
                'end_line': getattr(node, "end_lineno", node.lineno)
            }
            definitions.append(class_def)
            
            # Process all nodes within the class
            for child_node in ast.iter_child_nodes(node):
                process_node(child_node, name)
    
    # Process all top-level nodes
    for node in ast.iter_child_nodes(tree):
        process_node(node)
    
    return definitions


if __name__ == "__main__":
    summarizer = FileSummarizer()
    logger.info(summarizer.analyze_file("/Users/jjj/git/piano_trainer/src/piano_trainer.py"))
    # logger.info(summarizer.analyze_file("tac/utils/file_summarizer.py"))