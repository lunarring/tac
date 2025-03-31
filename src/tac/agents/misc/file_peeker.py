import os
from enum import Enum
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass
import argparse

from tac.core.llm import LLMClient, Message
from tac.utils.project_files import ProjectFiles
from tac.core.log_config import setup_logging
from tac.core.config import config

logger = setup_logging('tac.agents.misc.file_peeker')

class DetailLevel(Enum):
    """Detail levels for file content retrieval"""
    FULL_CODE = "full_code"
    DETAILED_SUMMARY = "detailed_summary"
    HIGH_LEVEL_SUMMARY = "high_level_summary"
    SKIP = "skip"

@dataclass
class FileRelevance:
    """Stores relevance information for a file"""
    path: str
    score: float
    detail_level: DetailLevel
    reason: str
    content: Optional[str] = None

class FilePeeker:
    """
    Agent that dynamically determines file relevance based on chat context
    and retrieves file content at appropriate detail levels.
    """
    
    def __init__(self, project_root: str = ".", summary_level: Optional[str] = None, max_files: Optional[int] = None, use_strong_llm: bool = True):
        """
        Initialize the FilePeeker agent.
        
        Args:
            project_root: Root directory of the project
            summary_level: Summary level to use ("high_level", "detailed", or "auto")
            max_files: Maximum number of files to include in context
            use_strong_llm: Whether to use the strong LLM for file analysis
        """
        self.project_files = ProjectFiles(project_root)
        self.use_strong_llm = use_strong_llm
        self.llm = LLMClient(llm_type="strong" if use_strong_llm else "weak")
        
        # Use provided values or fallback to config
        self.summary_level = summary_level or config.general.file_peeker_summary_level
        self.max_files = max_files or config.general.file_peeker_max_files
        
        logger.debug(f"FilePeeker initialized with summary_level={self.summary_level}, max_files={self.max_files}, use_strong_llm={use_strong_llm}")
        
    def analyze_chat_for_files(self, chat_text: str, max_files: Optional[int] = None) -> List[FileRelevance]:
        """
        Analyze chat text to determine which files are most relevant.
        
        Args:
            chat_text: The chat text to analyze
            max_files: Maximum number of files to return (overrides instance setting)
            
        Returns:
            List of FileRelevance objects
        """
        # Get all available files and their summaries
        summaries = self.project_files.get_all_summaries()
        file_paths = list(summaries["files"].keys())
        
        # Use provided max_files or instance setting
        max_files = max_files or self.max_files
        
        # If there are no files, return empty list
        if not file_paths:
            return []
        
        # Create a file list with summaries of the appropriate detail level
        file_info = []
        for file_path in file_paths:
            file_data = summaries["files"].get(file_path, {})
            
            # Get the appropriate summary based on the configured summary level
            if self.summary_level == "high_level" and "summary_high_level" in file_data:
                summary = file_data["summary_high_level"]
            elif self.summary_level == "detailed" and "summary_detailed" in file_data:
                summary = file_data["summary_detailed"]
            elif "summary_high_level" in file_data:
                # Default to high-level summary if no preference or detailed not available
                summary = file_data["summary_high_level"]
            else:
                summary = "No summary available"
                
            file_info.append(f"- {file_path}: {summary}")
        
        file_list = "\n".join(file_info)
        
        # Create a prompt for the LLM to analyze chat and rank files
        # If summary level is fixed (not auto), include it in the prompt
        detail_level_instructions = ""
        if self.summary_level == "high_level":
            detail_level_instructions = "Prefer 'high_level_summary' for most files unless there's a very strong relevance."
        elif self.summary_level == "detailed":
            detail_level_instructions = "Prefer 'detailed_summary' for relevant files instead of high level summaries."
        
        prompt = f"""
        Based on the following chat text, analyze which files are most relevant and determine the appropriate
        detail level for each file. Think carefully about which files would be most helpful for understanding 
        or completing the task described in the chat.
        
        Chat Text:
        {chat_text}
        
        Available Files with {'DETAILED' if self.summary_level == 'detailed' else 'HIGH-LEVEL'} summaries:
        {file_list}
        
        STEP 1: First analyze what the chat is requesting and what files could be relevant given the chat text. Priorize files that are central to the request, and put test files at the bottom.         
        
        STEP 2: For each potentially relevant file, assign:
        - A relevance score from 0.0-1.0 (higher = more relevant)
        - A detail level from:
          * 'full_code': Provide the complete code of a file when it's central to the request
          * 'detailed_summary': Return detailed summaries when understanding structure is important
          * 'high_level_summary': Return high level summary when just general understanding is needed
          * 'skip': Skip files with little to no relevance
        - A reason explaining WHY this file is relevant to the chat request
        
        {detail_level_instructions}
        
        Return the top {max_files} most relevant files in JSON format:
        [
          {{"path": "path/to/file1", "score": 0.95, "detail_level": "full_code", "reason": "This file contains the main implementation of X that needs to be modified as mentioned in the chat."}},
          {{"path": "path/to/file2", "score": 0.75, "detail_level": "detailed_summary", "reason": "Contains related functionality that would help understand the context."}},
          ...
        ]
        
        Only include files with relevance scores above 0.1. Sort by relevance score in descending order.
        """
        
        # Call LLM to analyze and rank files
        llm_response = self.llm.chat_completion(
            messages=[Message(role="user", content=prompt)]
        )
        
        # Parse the LLM response to extract file relevance info
        try:
            import json
            import re
            
            # Find the JSON array in the response
            json_match = re.search(r'\[\s*\{.*\}\s*\]', llm_response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                file_relevance_data = json.loads(json_str)
                
                # Create FileRelevance objects
                results = []
                for item in file_relevance_data:
                    try:
                        # If summary level is not auto, override the LLM's choice
                        if self.summary_level == "high_level" and item["detail_level"] == "detailed_summary":
                            detail_level = DetailLevel.HIGH_LEVEL_SUMMARY
                        elif self.summary_level == "detailed" and item["detail_level"] == "high_level_summary":
                            detail_level = DetailLevel.DETAILED_SUMMARY
                        else:
                            detail_level = DetailLevel(item["detail_level"])
                    except ValueError:
                        # Default to high level summary if the detail level is invalid
                        detail_level = DetailLevel.HIGH_LEVEL_SUMMARY
                    
                    # Extract reason, or use default if not provided
                    reason = item.get("reason", "No reason provided")
                    
                    results.append(FileRelevance(
                        path=item["path"],
                        score=float(item["score"]),
                        detail_level=detail_level,
                        reason=reason
                    ))
                
                return results[:max_files]
            
            logger.warning(f"Failed to parse LLM response: {llm_response}")
            return []
        
        except Exception as e:
            logger.error(f"Error parsing LLM response: {str(e)}")
            return []
    
    def get_file_content(self, file_relevance: FileRelevance) -> FileRelevance:
        """
        Retrieve the content of a file at the specified detail level.
        
        Args:
            file_relevance: FileRelevance object with path and detail level
            
        Returns:
            Updated FileRelevance object with content
        """
        abs_path = os.path.join(self.project_files.project_root, file_relevance.path)
        
        if file_relevance.detail_level == DetailLevel.SKIP:
            file_relevance.content = None
            return file_relevance
            
        # Check if we should extract specific functions based on the reason
        if self._should_extract_functions(file_relevance.reason):
            functions = self._extract_relevant_functions(abs_path, file_relevance.reason)
            if functions:
                file_relevance.content = functions
                return file_relevance
        
        # If no specific functions or not appropriate to extract, proceed with standard content retrieval
        if file_relevance.detail_level == DetailLevel.FULL_CODE:
            file_relevance.content = self.project_files.get_file_content(abs_path, use_summaries=False)
        elif file_relevance.detail_level == DetailLevel.DETAILED_SUMMARY:
            summary = self.project_files.get_file_summary(abs_path)
            if summary and "summary_detailed" in summary:
                file_relevance.content = summary["summary_detailed"]
            else:
                # Fallback to full code if detailed summary not available
                file_relevance.content = self.project_files.get_file_content(abs_path, use_summaries=False)
        elif file_relevance.detail_level == DetailLevel.HIGH_LEVEL_SUMMARY:
            summary = self.project_files.get_file_summary(abs_path)
            if summary and "summary_high_level" in summary:
                file_relevance.content = summary["summary_high_level"]
            else:
                # Fallback to detailed summary if high level not available
                file_relevance.content = self.project_files.get_file_content(abs_path, use_summaries=True)
        
        return file_relevance
    
    def _should_extract_functions(self, reason: str) -> bool:
        """
        Determine if we should extract specific functions based on the reason.
        
        Args:
            reason: The reason string from the LLM
            
        Returns:
            Boolean indicating whether to extract functions
        """
        # Keywords that suggest we should extract specific functions
        function_keywords = [
            'function', 'method', 'def ', 'implementation of', 
            'specifically', 'particular', 'specific part', 
            'only need the', 'just need the'
        ]
        
        return any(keyword in reason.lower() for keyword in function_keywords)
    
    def _extract_relevant_functions(self, file_path: str, reason: str) -> Optional[str]:
        """
        Extract specific functions from a file based on the reason.
        
        Args:
            file_path: Path to the file
            reason: The reason string from the LLM
            
        Returns:
            String with extracted functions or None if extraction failed
        """
        if not os.path.exists(file_path):
            return None
            
        # Get full file content
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Try to extract function or class names from the reason
        import re
        
        # Look for function names in the reason
        function_matches = re.findall(r'\b(\w+)\s*(?:function|method|implementation)\b', reason)
        function_matches += re.findall(r'function\s+(\w+)', reason)
        function_matches += re.findall(r'method\s+(\w+)', reason)
        function_matches += re.findall(r'def\s+(\w+)', reason)
        
        # Look for class names
        class_matches = re.findall(r'\b(\w+)\s*class\b', reason)
        class_matches += re.findall(r'class\s+(\w+)', reason)
        
        # Create a list of potential targets to extract
        targets = list(set(function_matches + class_matches))
        
        # If we have specific targets, try to extract them
        extracted_blocks = []
        
        if targets:
            file_ext = os.path.splitext(file_path)[1].lower()
            
            if file_ext == '.py':
                extracted_blocks = self._extract_python_elements(content, targets)
            elif file_ext in ['.js', '.ts', '.jsx', '.tsx']:
                extracted_blocks = self._extract_js_elements(content, targets)
            elif file_ext in ['.c', '.cpp', '.h', '.hpp']:
                extracted_blocks = self._extract_c_elements(content, targets)
            
            if extracted_blocks:
                prefix = "Extracted relevant sections from file:\n\n"
                return prefix + "\n\n".join(extracted_blocks)
        
        return None  # No specific functions could be extracted
    
    def _extract_python_elements(self, content: str, targets: List[str]) -> List[str]:
        """Extract Python functions and classes"""
        import ast
        import re
        
        extracted_blocks = []
        
        try:
            # Try to parse with AST for accurate extraction
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if (isinstance(node, ast.FunctionDef) or isinstance(node, ast.ClassDef)) and node.name in targets:
                    # Get the source code lines for this node
                    start_line = node.lineno
                    end_line = self._find_python_node_end(content, start_line)
                    
                    lines = content.splitlines()[start_line-1:end_line]
                    extracted_blocks.append(f"Lines {start_line}-{end_line}:\n" + "\n".join(lines))
        
        except SyntaxError:
            # Fallback to regex for syntax errors
            for target in targets:
                # Look for function definitions
                func_pattern = rf'def\s+{re.escape(target)}\s*\(.*?\).*?:'
                matches = list(re.finditer(func_pattern, content, re.DOTALL))
                
                for match in matches:
                    block_start = content[:match.start()].count('\n') + 1
                    func_code = self._extract_block_from_position(content, match.start())
                    if func_code:
                        block_end = block_start + func_code.count('\n')
                        extracted_blocks.append(f"Lines {block_start}-{block_end}:\n{func_code}")
                
                # Look for class definitions
                class_pattern = rf'class\s+{re.escape(target)}\s*(?:\(.*?\))?.*?:'
                matches = list(re.finditer(class_pattern, content, re.DOTALL))
                
                for match in matches:
                    block_start = content[:match.start()].count('\n') + 1
                    class_code = self._extract_block_from_position(content, match.start())
                    if class_code:
                        block_end = block_start + class_code.count('\n')
                        extracted_blocks.append(f"Lines {block_start}-{block_end}:\n{class_code}")
        
        return extracted_blocks
    
    def _find_python_node_end(self, content: str, start_line: int) -> int:
        """Find the end line of a Python block starting at start_line"""
        lines = content.splitlines()
        if start_line > len(lines):
            return start_line
            
        # Get the indentation of the definition line
        def_line = lines[start_line-1]
        def_indent = len(def_line) - len(def_line.lstrip())
        
        # Find where the block ends (next line with same or less indentation)
        end_line = start_line
        for i in range(start_line, len(lines)):
            line = lines[i]
            if line.strip() and not line.strip().startswith('#'):  # Ignore empty lines and comments
                line_indent = len(line) - len(line.lstrip())
                if line_indent <= def_indent:
                    return i
            end_line = i + 1
            
        return end_line
    
    def _extract_block_from_position(self, content: str, pos: int) -> Optional[str]:
        """Extract a code block from a position using indentation logic"""
        lines = content.splitlines()
        line_idx = content[:pos].count('\n')
        
        if line_idx >= len(lines):
            return None
            
        # Get the indentation of the definition line
        def_line = lines[line_idx]
        def_indent = len(def_line) - len(def_line.lstrip())
        
        # Collect the block
        block_lines = [def_line]
        
        for i in range(line_idx + 1, len(lines)):
            line = lines[i]
            if not line.strip():  # Keep empty lines
                block_lines.append(line)
                continue
                
            line_indent = len(line) - len(line.lstrip())
            if line_indent <= def_indent and line.strip():
                # End of block found
                break
                
            block_lines.append(line)
            
        return "\n".join(block_lines)
    
    def _extract_js_elements(self, content: str, targets: List[str]) -> List[str]:
        """Extract JavaScript/TypeScript functions and classes"""
        import re
        
        extracted_blocks = []
        
        for target in targets:
            # Function declarations
            patterns = [
                rf'function\s+{re.escape(target)}\s*\(.*?\).*?{{',  # function declaration
                rf'const\s+{re.escape(target)}\s*=\s*function.*?{{',  # function expression
                rf'let\s+{re.escape(target)}\s*=\s*function.*?{{',
                rf'var\s+{re.escape(target)}\s*=\s*function.*?{{',
                rf'const\s+{re.escape(target)}\s*=\s*\(.*?\)\s*=>.*?{{',  # arrow function
                rf'let\s+{re.escape(target)}\s*=\s*\(.*?\)\s*=>.*?{{',
                rf'var\s+{re.escape(target)}\s*=\s*\(.*?\)\s*=>.*?{{',
                rf'{re.escape(target)}\s*\(.*?\)\s*{{',  # method shorthand
                rf'class\s+{re.escape(target)}\s*{{',  # class
                rf'class\s+{re.escape(target)}\s+extends\s+\w+\s*{{'  # class with extends
            ]
            
            for pattern in patterns:
                matches = list(re.finditer(pattern, content, re.DOTALL))
                
                for match in matches:
                    block_start = content[:match.start()].count('\n') + 1
                    block_code = self._extract_js_block_from_position(content, match.start())
                    if block_code:
                        block_end = block_start + block_code.count('\n')
                        extracted_blocks.append(f"Lines {block_start}-{block_end}:\n{block_code}")
        
        return extracted_blocks
    
    def _extract_js_block_from_position(self, content: str, pos: int) -> Optional[str]:
        """Extract a JavaScript code block using brace matching"""
        start_idx = content.find('{', pos)
        if start_idx == -1:
            return None
            
        # Count lines until opening brace
        line_start = content[:start_idx].count('\n') + 1
        
        # Find the closing brace by matching braces
        brace_count = 1
        idx = start_idx + 1
        
        while idx < len(content) and brace_count > 0:
            if content[idx] == '{':
                brace_count += 1
            elif content[idx] == '}':
                brace_count -= 1
            idx += 1
            
        if brace_count == 0:
            end_idx = idx
            # Get the line range
            block_text = content[pos:end_idx]
            return block_text
            
        return None
    
    def _extract_c_elements(self, content: str, targets: List[str]) -> List[str]:
        """Extract C/C++ functions and classes"""
        import re
        
        extracted_blocks = []
        
        for target in targets:
            # Function declarations (with various return types)
            patterns = [
                rf'\w+\s+{re.escape(target)}\s*\(.*?\)\s*{{',  # Function with return type
                rf'class\s+{re.escape(target)}\s*{{',  # class
                rf'struct\s+{re.escape(target)}\s*{{'  # struct
            ]
            
            for pattern in patterns:
                matches = list(re.finditer(pattern, content, re.DOTALL))
                
                for match in matches:
                    block_start = content[:match.start()].count('\n') + 1
                    block_code = self._extract_js_block_from_position(content, match.start())  # Reuse JS block extractor
                    if block_code:
                        block_end = block_start + block_code.count('\n')
                        extracted_blocks.append(f"Lines {block_start}-{block_end}:\n{block_code}")
        
        return extracted_blocks
    
    def generate_context(self, chat_text: str, max_files: Optional[int] = None, token_budget: int = 10000, always_full_content: bool = False) -> str:
        """
        Generate context for a coding agent based on chat text.
        
        Args:
            chat_text: The chat text to analyze
            max_files: Maximum number of files to include (overrides instance setting)
            token_budget: Approximate token budget for context
            always_full_content: If True, always gets full file content regardless of detail level
            
        Returns:
            Formatted context string for the agent
        """
        # Use provided max_files or instance setting
        max_files = max_files or self.max_files
        
        # Analyze chat to determine file relevance
        relevant_files = self.analyze_chat_for_files(chat_text, max_files)
        
        # Get content for each file
        for i, file_rel in enumerate(relevant_files):
            relevant_files[i] = self.get_file_content(file_rel)
            
            # If always_full_content is True, get the full file content regardless of detail level
            if always_full_content and file_rel.detail_level != DetailLevel.SKIP:
                abs_path = os.path.join(self.project_files.project_root, file_rel.path)
                if os.path.exists(abs_path):
                    with open(abs_path, 'r', encoding='utf-8') as f:
                        relevant_files[i].content = f.read()
        
        # Format the context string
        context_parts = []
        for file_rel in relevant_files:
            if file_rel.detail_level == DetailLevel.SKIP or not file_rel.content:
                continue
                
            # Create a clear header based on detail level
            if file_rel.detail_level == DetailLevel.FULL_CODE:
                header = f"FILE (FULL CODE): {file_rel.path}"
            elif file_rel.detail_level == DetailLevel.DETAILED_SUMMARY:
                header = f"FILE (DETAILED SUMMARY): {file_rel.path}"
            elif file_rel.detail_level == DetailLevel.HIGH_LEVEL_SUMMARY:
                header = f"FILE (HIGH-LEVEL SUMMARY): {file_rel.path}"
            
            # Add relevance info and separators
            relevance_info = f"Relevance: {file_rel.score:.2f} - {file_rel.reason}"
            separator = "=" * 80
            
            context_parts.append(f"{separator}\n{header}\n{relevance_info}\n{separator}\n\n{file_rel.content}\n\nEND FILE")
        
        return "\n\n".join(context_parts)
    
    def peek_files(self, chat_text: str, max_files: Optional[int] = None, always_full_content: bool = False) -> Dict[str, List[Dict]]:
        """
        Main method to analyze chat and get file information at different detail levels.
        
        Args:
            chat_text: The chat text to analyze
            max_files: Maximum number of files to include (overrides instance setting)
            always_full_content: If True, always gets full file content regardless of detail level
            
        Returns:
            Dictionary with files categorized by detail level
        """
        # Use provided max_files or instance setting
        max_files = max_files or self.max_files
        
        # Analyze chat to determine file relevance
        relevant_files = self.analyze_chat_for_files(chat_text, max_files)
        
        # Get content for each file
        for i, file_rel in enumerate(relevant_files):
            relevant_files[i] = self.get_file_content(file_rel)
            
            # If always_full_content is True, get the full file content regardless of detail level
            if always_full_content and file_rel.detail_level != DetailLevel.SKIP:
                abs_path = os.path.join(self.project_files.project_root, file_rel.path)
                if os.path.exists(abs_path):
                    with open(abs_path, 'r', encoding='utf-8') as f:
                        relevant_files[i].content = f.read()
        
        # Organize files by detail level
        result = {
            "full_code": [],
            "detailed_summary": [],
            "high_level_summary": [],
            "skip": []
        }
        
        for file_rel in relevant_files:
            level_key = file_rel.detail_level.value
            result[level_key].append({
                "path": file_rel.path,
                "score": file_rel.score,
                "reason": file_rel.reason,
                "content": file_rel.content
            })
        
        return result


if __name__ == "__main__":
    # Set up command line arguments
    parser = argparse.ArgumentParser(description='FilePeeker: Analyze chat text to determine relevant files')
    parser.add_argument('--chat', '-c', type=str, default="I need help with the ProjectFiles class. How do I get file summaries?",
                        help='Chat text to analyze')
    parser.add_argument('--max-files', '-m', type=int, default=None,
                        help='Maximum number of files to include (default from config)')
    parser.add_argument('--project-root', '-p', type=str, default=".",
                        help='Project root directory')
    parser.add_argument('--output', '-o', choices=['context', 'categorized', 'both'], default='both',
                        help='Output format: context, categorized, or both')
    parser.add_argument('--summary-level', '-s', choices=['high_level', 'detailed', 'auto'], default=None,
                        help='Summary level to use (default from config)')
    parser.add_argument('--weak-llm', action='store_true',
                        help='Use weak LLM instead of strong LLM for file analysis')
    parser.add_argument('--preview-only', '-P', action='store_true',
                        help='Show only previews of content instead of full content')
    parser.add_argument('--force-full-content', '-F', action='store_true',
                        help='Always show full file content regardless of the selected detail level')
    parser.add_argument('--rich', '-r', action='store_true',
                        help='Use rich formatting for output when available')
    
    args = parser.parse_args()
    
    # Example usage of FilePeeker
    peeker = FilePeeker(
        project_root=args.project_root, 
        summary_level=args.summary_level,
        max_files=args.max_files,
        use_strong_llm=not args.weak_llm
    )
    
    print(f"Analyzing chat: '{args.chat}'")
    print(f"Using summary level: {peeker.summary_level}, max files: {peeker.max_files}, model: {'weak' if args.weak_llm else 'strong'}\n")
    
    # Import rich if available and requested
    rich_console = None
    if args.rich:
        try:
            from rich.console import Console
            from rich.syntax import Syntax
            from rich.panel import Panel
            rich_console = Console()
            print("Using rich formatting for output")
        except ImportError:
            print("Rich not available, using standard formatting")
    
    # Get results based on the selected output format
    if args.output in ['context', 'both']:
        # Get file context for agent
        context = peeker.generate_context(args.chat, always_full_content=args.force_full_content)
        print("Generated context for coding agent:")
        print(context)
        
        if args.output == 'both':
            print("\n" + "-" * 50 + "\n")
    
    if args.output in ['categorized', 'both']:
        # Get categorized file information
        results = peeker.peek_files(args.chat, always_full_content=args.force_full_content)
        
        # Print results by category
        for level, files in results.items():
            if files:
                if rich_console:
                    rich_console.print(f"\n[bold]{level.upper()}:[/bold]")
                else:
                    print(f"\n{level.upper()}:")
                    
                for file in files:
                    file_path = file['path']
                    score = file['score']
                    reason = file['reason']
                    content = file['content']
                    
                    if rich_console:
                        # Use rich formatting
                        rich_console.print(f"  [bold cyan]{file_path}[/bold cyan] (score: {score:.2f})")
                        if level != "skip" and content:
                            rich_console.print(f"  [italic]{reason}[/italic]")
                            
                            if not args.preview_only:
                                # Determine the language for syntax highlighting
                                language = "text"
                                if file_path.endswith(".py"):
                                    language = "python"
                                elif file_path.endswith((".js", ".jsx")):
                                    language = "javascript"
                                elif file_path.endswith((".ts", ".tsx")):
                                    language = "typescript"
                                elif file_path.endswith((".html", ".htm")):
                                    language = "html"
                                elif file_path.endswith(".css"):
                                    language = "css"
                                    
                                # Show the full content with syntax highlighting
                                syntax = Syntax(content, language, theme="monokai", line_numbers=True)
                                rich_console.print(Panel(syntax, expand=False))
                            else:
                                # Show preview
                                preview = content[:100] + "..." if len(content) > 100 else content
                                rich_console.print(Panel(preview, expand=False))
                    else:
                        # Standard formatting
                        print(f"  {file_path} (score: {score:.2f})")
                        if level != "skip" and content:
                            print(f"  Reason: {reason}")
                            print(f"  {'-' * 30}")
                            if not args.preview_only:
                                # Show the full content
                                print(f"{content}")
                            else:
                                # Show preview of content
                                preview = content[:100] + "..." if len(content) > 100 else content
                                print(f"  {preview}")
                            print(f"  {'-' * 30}\n") 