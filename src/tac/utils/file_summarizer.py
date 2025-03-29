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
<high_level_summary>
Write a high-level summary of the entire file here. Describe what this file contains, e.g. if there are classes, functions, tests, etc.
</high_level_summary>

<detailed_summary>
Each entry must follow this exact format:

FunctionName (line X:Y): Description of what the function does, its parameters, return values, and any notable interactions with other functions or classes.

ClassName (line X:Y): Description of the class purpose and its key characteristics.
  - method1: What this method does
  - method2: What this method does and how it relates to method1

Example:
extract_code_definitions (line 580:620): Parses Python code using the ast module to extract all function and class definitions along with their line numbers. Returns a list of dictionaries containing type, name, start_line, and end_line for each definition.

FileSummarizer (line 12:579): Class that provides functionality to analyze and summarize code files using LLM-based analysis.
  - analyze_file: Main method that processes a file and returns a structured summary
  - _generate_detailed_summary: Core method that uses LLM to produce a detailed analysis of code
</detailed_summary>

IMPORTANT: Make sure to include ALL classes and functions in your analysis, not just the first few. The file may contain multiple classes and functions that all need to be described.
"""
        elif file_type in ["javascript", "typescript"]:
            prompt += """You are a senior web developer who specializes in Three.js. Provide a concise analysis of the code's functions, classes, and components. Format your response as follows:
<high_level_summary>
Write a high-level summary of the entire file here.
</high_level_summary>

<detailed_summary>
Each entry must follow this exact format:

FunctionName (line X:Y): Description focusing on Three.js functionality, parameters, return values, and rendering techniques.

ClassName (line X:Y): Description of the class purpose in the Three.js context.
  - method1: What this method does for 3D rendering
  - method2: How this method affects the scene or rendering pipeline

Example:
createScene (line 10:25): Initializes a Three.js scene with a PerspectiveCamera and WebGLRenderer. Sets up initial lighting with an AmbientLight and DirectionalLight.

Particle (line 30:100): Class representing individual particles in a particle system.
  - update: Updates particle position and opacity based on lifespan
  - applyForce: Adds external forces to particle velocity
</detailed_summary>

IMPORTANT: Make sure to include ALL functions, classes and components in your analysis, not just the first few. The file may contain multiple functions, classes and Three.js-specific code that all need to be described.
"""
        elif file_type == "html":
            prompt += """You are a senior web developer who specializes in Three.js web applications. Provide a concise analysis of this HTML file that likely contains or references Three.js code. Format your response as follows:
<high_level_summary>
Write a high-level summary of the entire file here.
</high_level_summary>

<detailed_summary>
Each entry must follow this exact format:

ElementName (line X:Y): Description focusing on its role in the Three.js application, including any attributes, src references, or connections to the 3D rendering.

Example:
canvas (line 15:15): Main rendering canvas with id="scene" where the Three.js application draws. Set with width and height attributes to match window dimensions.

ScriptSection (line 25:100): Contains the main Three.js initialization code including scene setup, camera positioning, and render loop. Imports Three.js from CDN and sets up the OrbitControls.
</detailed_summary>

IMPORTANT: Make sure to analyze ALL important elements in the file, not just the first few, with special attention to Three.js-related components.
"""
        elif file_type == "glsl":
            prompt += """You are a senior graphics programmer who specializes in Three.js and GLSL shaders. Provide a concise analysis of this shader code. Format your response as follows:
<high_level_summary>
Write a high-level summary of what this shader does.
</high_level_summary>

<detailed_summary>
Each entry must follow this exact format:

uniform/varying/attribute Name (line X:Y): Description of its purpose, type, and how it affects the rendering.

functionName (line X:Y): Mathematical operations performed, visual effect created, and any key algorithms implemented.

Example:
uniform float uTime (line 5:5): Float uniform that controls time-based animations, used to create waves and movement effects.

varying vec2 vUv (line 7:7): Texture coordinates passed from vertex to fragment shader, used for texture mapping and distortion effects.

main (line 20:45): Fragment shader entry point that calculates the final color based on noise patterns and lighting models. Implements a procedural pattern using simplex noise and combines it with dynamic lighting.
</detailed_summary>

IMPORTANT: Make sure to describe ALL important components of the shader, not just the first few, and explain the visual effect they create.
"""
        else:  # json or generic format
            prompt += """You are a senior developer who specializes in Three.js applications. Provide a concise analysis of this file. Format your response as follows:
<high_level_summary>
Write a high-level summary of the entire file here.
</high_level_summary>

<detailed_summary>
Each entry must follow this exact format:

KeyName (line X:Y): Description of what this section contains and how it relates to Three.js functionality.

Example:
scene (line 5:20): Contains configuration for the main Three.js scene including camera properties, renderer settings, and initial object placements.

materials (line 25:50): Defines material properties used in the application, including custom shaders, textures, and lighting parameters for PBR rendering.
</detailed_summary>

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

        return response

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
                        "high_level_summary": "Empty or non-Python file with no definitions.",
                        "summary_high_level": "Empty or non-Python file with no definitions.",
                        "summary_detailed": "",
                        "content": "Empty or non-Python file with no definitions."
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
                        "high_level_summary": f"{file_type.capitalize()} file with no detectable functions or classes.",
                        "summary_high_level": f"{file_type.capitalize()} file with no detectable functions or classes.",
                        "summary_detailed": "",
                        "content": f"High-level summary: {file_type.capitalize()} file with no detectable functions or classes."
                    }

            # Generate summary based on extracted definitions
            summary = self._generate_detailed_summary(self.current_file_content, functions, classes, file_type)
            if summary.startswith("Error:"):
                return {
                    "error": summary,
                    "high_level_summary": None,
                    "summary_high_level": None,
                    "summary_detailed": None,
                    "content": None
                }
                
            # Parse the high-level summary and detailed summary from the response
            high_level_summary = ""
            detailed_summary = ""
            
            # Extract high-level summary
            high_level_match = re.search(r'<high_level_summary>(.*?)</high_level_summary>', summary, re.DOTALL)
            if high_level_match:
                high_level_summary = high_level_match.group(1).strip()
            
            # Extract detailed summary
            detailed_match = re.search(r'<detailed_summary>(.*?)</detailed_summary>', summary, re.DOTALL)
            if detailed_match:
                detailed_summary = detailed_match.group(1).strip()
            
            # If the tags aren't found, use the original summary format
            if not high_level_summary and not detailed_summary:
                # Try to extract high level summary from the first line
                lines = summary.strip().split('\n')
                if lines and lines[0].startswith("High-level summary:"):
                    high_level_summary = lines[0].replace("High-level summary:", "").strip()
                    detailed_summary = '\n'.join(lines[1:]).strip()
                else:
                    high_level_summary = "Summary not properly formatted"
                    detailed_summary = summary
            
            # Create combined content for backward compatibility
            content = f"High-level summary: {high_level_summary}\n\n{detailed_summary}"
                
            return {
                "error": None,
                "high_level_summary": high_level_summary,
                "summary_high_level": high_level_summary,
                "summary_detailed": detailed_summary,
                "content": content
            }
            
        except Exception as e:
            logger.error(f"Error analyzing file {file_path}: {str(e)}")
            return {
                "error": f"Unexpected error: {str(e)}",
                "high_level_summary": None,
                "summary_high_level": None,
                "summary_detailed": None,
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