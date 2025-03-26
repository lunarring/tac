import os
import ast
import re
from datetime import datetime
from typing import Dict, List, Optional
from tac.core.llm import LLMClient, Message
from tac.core.config import config
import logging
from tac.core.log_config import setup_logging
logger = setup_logging('tac.utils.file_summarizer')

class FileSummarizer:
    """Class for summarizing code files using LLM analysis"""
    
    def __init__(self):
        self.llm_client = LLMClient(llm_type="weak")
        self.timeout = config.general.summarizer_timeout

    def _generate_detailed_summary(self, code: str, functions: list, classes: list, file_type: str = "python") -> str:
        """Generate a detailed analysis of the code by merging summarization responsibilities."""
        prompt = f"Analyze the following {file_type} code in detail.\n"
        if functions:
            prompt += "Functions:\n" + "\n".join([f"- {f}" for f in functions]) + "\n"
        if classes:
            prompt += "Classes and their methods:\n"
            for cls in classes:
                methods = ", ".join(cls.get("methods", []))
                prompt += f"- {cls['name']}: {methods}\n"
        prompt += f"\nFull Code:\n<code>\n{code}\n</code>\n"
        
        if file_type == "python":
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
        elif file_type in ["javascript", "typescript"]:
            prompt += """You are a senior web developer who specializes in Three.js. Provide a concise analysis of the code's functions, classes, and components. Format your response as follows:
Start with a high-level summary of the entire file.
Then for each function/class/component, start a new line with the exact name, followed by a colon and the description.
Focus on Three.js-specific functionality, 3D rendering concepts, and any graphical techniques used.
Keep descriptions technical and highlight interactions between parts of the code.

High-level summary: (insert high level summary here)
Function/Class/Component 1 (line begin:line end): (insert description here)
Function/Class/Component 2 (line begin:line end): (insert description here)

IMPORTANT: Make sure to include ALL functions, classes and components in your analysis, not just the first few. The file may contain multiple functions, classes and Three.js-specific code that all need to be described.
"""
        elif file_type == "html":
            prompt += """You are a senior web developer who specializes in Three.js web applications. Provide a concise analysis of this HTML file that likely contains or references Three.js code. Format your response as follows:
Start with a high-level summary of the entire file.
Then describe all the key sections and elements in the file, with a focus on Three.js canvas, scripts, and imports.
Highlight how this file connects to any Three.js functionality.

High-level summary: (insert high level summary here)
Element/Section 1 (line begin:line end): (insert description here)
Element/Section 2 (line begin:line end): (insert description here)

IMPORTANT: Make sure to analyze ALL important elements in the file, not just the first few, with special attention to Three.js-related components.
"""
        elif file_type == "glsl":
            prompt += """You are a senior graphics programmer who specializes in Three.js and GLSL shaders. Provide a concise analysis of this shader code. Format your response as follows:
Start with a high-level summary of what this shader does.
Then for each function, uniform, varying, or significant section, start a new line with the name followed by a colon and description.
Focus on the graphical techniques, mathematical operations, and visual effects this shader creates.

High-level summary: (insert description of the shader's purpose and visual effect)
Function/Uniform/Section 1 (line begin:line end): (insert description here)
Function/Uniform/Section 2 (line begin:line end): (insert description here)

IMPORTANT: Make sure to describe ALL important components of the shader, not just the first few, and explain the visual effect they create.
"""
        else:  # json or generic format
            prompt += """You are a senior developer who specializes in Three.js applications. Provide a concise analysis of this file. Format your response as follows:
Start with a high-level summary of the entire file.
Then for each section or key component, provide a brief description.
Focus on how this content relates to Three.js functionality.

High-level summary: (insert high level summary here)
Section 1 (line begin:line end): (insert description here)
Section 2 (line begin:line end): (insert description here)

IMPORTANT: Make sure to analyze ALL important components in the file, not just the first few.
"""
        
        if file_type == "python":
            system_prompt = "You are a Python code analysis expert. Provide clear, detailed technical summaries of code structures. Make sure to analyze ALL classes and functions in the code, not just the first few."
        else:
            system_prompt = f"You are a {file_type} code analysis expert specializing in Three.js applications. Provide clear, detailed technical summaries focusing on 3D graphics concepts and implementations."
        
        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=prompt)
        ]

        response = self.llm_client.chat_completion(messages)
        
        # Create a mapping of names to their line numbers
        name_to_lines = {}
        for func in functions:
            if " (lines " in func:
                # Extract name and line numbers from the format "name (lines start-end)"
                name = func.split(" (lines ")[0]
                start, end = func.split(" (lines ")[1].rstrip(")").split("-")
                name_to_lines[name] = (start, end)
        
        for cls in classes:
            if isinstance(cls, dict) and "name" in cls and " (lines " in cls["name"]:
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

    def _detect_file_type(self, file_path: str) -> str:
        """Detect file type based on extension"""
        ext = os.path.splitext(file_path)[1].lower()
        
        if ext == '.py':
            return "python"
        elif ext in ['.js', '.mjs']:
            return "javascript"
        elif ext in ['.ts', '.tsx']:
            return "typescript"
        elif ext == '.html':
            return "html"
        elif ext in ['.glsl', '.vert', '.frag', '.shader']:
            return "glsl"
        elif ext == '.json':
            return "json"
        else:
            return "generic"

    def _extract_js_definitions(self, code: str) -> List[Dict]:
        """Extract function and class definitions from JavaScript/TypeScript code"""
        definitions = []
        
        # Regular expressions for matching JS/TS definitions
        patterns = {
            'function': r'function\s+([A-Za-z0-9_$]+)\s*\(',  # function declaration
            'arrow_function': r'(const|let|var)\s+([A-Za-z0-9_$]+)\s*=\s*(\([^)]*\)|[A-Za-z0-9_$]+)\s*=>',  # arrow function
            'function_expr': r'(const|let|var)\s+([A-Za-z0-9_$]+)\s*=\s*function',  # function expression
            'method': r'([A-Za-z0-9_$]+)\s*:\s*function',  # object method
            'method_short': r'([A-Za-z0-9_$]+)\s*\([^)]*\)\s*{',  # method shorthand
            'class': r'class\s+([A-Za-z0-9_$]+)',  # class declaration
        }
        
        # Process the code line by line to get line numbers
        lines = code.split('\n')
        for i, line in enumerate(lines):
            line_num = i + 1  # 1-indexed line number
            
            for def_type, pattern in patterns.items():
                matches = re.finditer(pattern, line)
                for match in matches:
                    if def_type == 'function':
                        name = match.group(1)
                        definition = {
                            'type': 'function',
                            'name': name,
                            'start_line': line_num,
                            'end_line': self._find_closing_bracket(lines, line_num) or line_num
                        }
                        definitions.append(definition)
                    elif def_type == 'arrow_function':
                        name = match.group(2)
                        definition = {
                            'type': 'function',
                            'name': name,
                            'start_line': line_num,
                            'end_line': self._find_closing_bracket(lines, line_num) or line_num
                        }
                        definitions.append(definition)
                    elif def_type == 'function_expr':
                        name = match.group(2)
                        definition = {
                            'type': 'function',
                            'name': name,
                            'start_line': line_num,
                            'end_line': self._find_closing_bracket(lines, line_num) or line_num
                        }
                        definitions.append(definition)
                    elif def_type == 'method':
                        name = match.group(1)
                        definition = {
                            'type': 'method',
                            'name': name,
                            'start_line': line_num,
                            'end_line': self._find_closing_bracket(lines, line_num) or line_num
                        }
                        definitions.append(definition)
                    elif def_type == 'method_short':
                        name = match.group(1)
                        definition = {
                            'type': 'method',
                            'name': name,
                            'start_line': line_num,
                            'end_line': self._find_closing_bracket(lines, line_num) or line_num
                        }
                        definitions.append(definition)
                    elif def_type == 'class':
                        name = match.group(1)
                        definition = {
                            'type': 'class',
                            'name': name,
                            'start_line': line_num,
                            'end_line': self._find_closing_bracket(lines, line_num) or line_num
                        }
                        definitions.append(definition)
        
        return definitions

    def _find_closing_bracket(self, lines: List[str], start_line: int) -> Optional[int]:
        """Find the line number of the closing bracket matching an opening bracket"""
        stack = 0
        started = False
        
        for i in range(start_line - 1, len(lines)):
            line = lines[i]
            
            for char in line:
                if char == '{':
                    stack += 1
                    started = True
                elif char == '}':
                    stack -= 1
                    if started and stack == 0:
                        return i + 1  # 1-indexed line number
            
        return None  # No closing bracket found

    def _extract_html_sections(self, code: str) -> List[Dict]:
        """Extract key sections from HTML files"""
        definitions = []
        
        # Regular expressions for matching HTML elements of interest
        patterns = {
            'script': r'<script[^>]*>(.*?)</script>',
            'canvas': r'<canvas[^>]*id=["\'"]([^"\']+)["\'][^>]*>',
            'three_import': r'<script[^>]*src=["\'](.*?three.*?\.js)["\'][^>]*>',
            'container': r'<div[^>]*id=["\'"]([^"\']+)["\'][^>]*>',
        }
        
        # Process the code line by line to get line numbers
        lines = code.split('\n')
        
        for pattern_name, pattern in patterns.items():
            # Use re.DOTALL for script pattern to match across lines
            flags = re.DOTALL if pattern_name == 'script' else 0
            for match in re.finditer(pattern, code, flags):
                # Find the line number of this match
                start_pos = match.start()
                end_pos = match.end()
                
                # Count newlines to find line numbers
                start_line = code[:start_pos].count('\n') + 1
                end_line = code[:end_pos].count('\n') + 1
                
                if pattern_name == 'script':
                    # For scripts, try to identify if it's a Three.js script
                    script_content = match.group(1)
                    if 'three' in script_content.lower() or 'scene' in script_content.lower() or 'renderer' in script_content.lower():
                        name = "Three.js Script"
                    else:
                        name = "Script Block"
                else:
                    # For other elements, use the ID if available
                    if match.groups():
                        name = f"{pattern_name.capitalize()}: {match.group(1)}"
                    else:
                        name = f"{pattern_name.capitalize()} Element"
                
                definition = {
                    'type': pattern_name,
                    'name': name,
                    'start_line': start_line,
                    'end_line': end_line
                }
                definitions.append(definition)
        
        return definitions

    def _extract_glsl_sections(self, code: str) -> List[Dict]:
        """Extract key sections from GLSL shader files"""
        definitions = []
        
        # Regular expressions for matching GLSL elements
        patterns = {
            'uniform': r'uniform\s+\w+\s+(\w+)',
            'varying': r'varying\s+\w+\s+(\w+)',
            'attribute': r'attribute\s+\w+\s+(\w+)',
            'function': r'(void|float|vec\d|mat\d)\s+(\w+)\s*\('
        }
        
        # Process the code line by line to get line numbers
        lines = code.split('\n')
        for i, line in enumerate(lines):
            line_num = i + 1
            
            for def_type, pattern in patterns.items():
                matches = re.finditer(pattern, line)
                for match in matches:
                    if def_type == 'function':
                        name = match.group(2)
                        end_line = self._find_closing_bracket(lines, line_num) or line_num
                    else:
                        name = match.group(1)
                        end_line = line_num
                    
                    definition = {
                        'type': def_type,
                        'name': name,
                        'start_line': line_num,
                        'end_line': end_line
                    }
                    definitions.append(definition)
        
        # Also add main if it exists
        if 'void main()' in code or 'void main(' in code:
            main_line = 0
            for i, line in enumerate(lines):
                if 'void main(' in line or 'void main()' in line:
                    main_line = i + 1
                    break
            
            if main_line > 0:
                end_line = self._find_closing_bracket(lines, main_line) or main_line
                definitions.append({
                    'type': 'function',
                    'name': 'main',
                    'start_line': main_line,
                    'end_line': end_line
                })
        
        return definitions

    def _extract_json_sections(self, code: str) -> List[Dict]:
        """Extract key sections from JSON files"""
        definitions = []
        
        try:
            # Parse JSON to find top-level keys
            import json
            data = json.loads(code)
            
            # Process the code line by line to estimate line numbers
            lines = code.split('\n')
            
            for key in data.keys():
                # Simple estimation - find the line containing this key
                for i, line in enumerate(lines):
                    if f'"{key}"' in line or f"'{key}'" in line:
                        start_line = i + 1
                        
                        # Estimate the end line based on content size
                        content = json.dumps(data[key])
                        size = len(content.split('\n'))
                        end_line = min(start_line + size, len(lines))
                        
                        definition = {
                            'type': 'json_section',
                            'name': key,
                            'start_line': start_line,
                            'end_line': end_line
                        }
                        definitions.append(definition)
                        break
        except:
            # If JSON parsing fails, create a single definition for the whole file
            definitions.append({
                'type': 'json_file',
                'name': 'JSON Content',
                'start_line': 1,
                'end_line': len(code.split('\n'))
            })
        
        return definitions

    def analyze_file(self, file_path: str) -> Dict:
        """Analyze a single file and return its summary"""
        try:
            # Detect file type
            file_type = self._detect_file_type(file_path)
            
            with open(file_path, 'r', encoding='utf-8') as f:
                self.current_file_content = f.read()

            functions = []
            classes = []
            
            # Extract definitions based on file type
            if file_type == "python":
                # Use extract_code_definitions to get functions and classes with line numbers
                definitions = extract_code_definitions(self.current_file_content)
                
                # If no functions or classes found, return early
                if not definitions:
                    return {
                        "error": None,
                        "content": "High-level summary: Empty or non-Python file with no definitions."
                    }
                
                # Process Python definitions
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
            
            elif file_type in ["javascript", "typescript"]:
                definitions = self._extract_js_definitions(self.current_file_content)
                
                # Process JS/TS definitions
                methods_by_class = {}
                
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
                        # For methods, try to associate with a class if possible
                        parts = defn['name'].split('.')
                        method_str = f"{defn['name']} (lines {defn['start_line']}-{defn['end_line']})"
                        functions.append(method_str)  # Add all methods to functions list
                        
                        # If the method name has a dot, it might be part of a class
                        if len(parts) > 1:
                            class_name = parts[0]
                            if class_name in methods_by_class:
                                methods_by_class[class_name].append(method_str)
                
                # Add methods to their classes
                for cls in classes:
                    class_name = cls["name"].split(" (lines ")[0]
                    if class_name in methods_by_class:
                        cls["methods"] = methods_by_class[class_name]
            
            elif file_type == "html":
                definitions = self._extract_html_sections(self.current_file_content)
                
                # Process HTML sections
                for defn in definitions:
                    functions.append(f"{defn['name']} (lines {defn['start_line']}-{defn['end_line']})")
            
            elif file_type == "glsl":
                definitions = self._extract_glsl_sections(self.current_file_content)
                
                # Process GLSL sections
                for defn in definitions:
                    functions.append(f"{defn['name']} (lines {defn['start_line']}-{defn['end_line']})")
            
            elif file_type == "json":
                definitions = self._extract_json_sections(self.current_file_content)
                
                # Process JSON sections
                for defn in definitions:
                    functions.append(f"{defn['name']} (lines {defn['start_line']}-{defn['end_line']})")
            
            # If no definitions found, create a simple summary
            if not functions and not classes:
                if file_type in ["html", "glsl", "json"]:
                    # For these types, still analyze the whole file
                    functions.append(f"Full Content (lines 1-{len(self.current_file_content.split())})")
                else:
                    return {
                        "error": None,
                        "content": f"High-level summary: {file_type.capitalize()} file with no detectable functions or classes."
                    }

            # Generate summary based on extracted definitions
            summary = self._generate_detailed_summary(self.current_file_content, functions, classes, file_type)
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