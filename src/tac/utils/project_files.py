import os
import json
import hashlib
import re
import fnmatch
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Union
from tac.utils.file_summarizer import FileSummarizer
from tac.core.config import config
from tac.core.log_config import setup_logging
from tqdm import tqdm
import ast
import concurrent.futures
import threading

logger = setup_logging('tac.utils.project_files')

class ProjectFiles:
    """Manages project-wide file summaries and tracking"""
    
    def __init__(self, project_root: str = "."):
        self.project_root = os.path.abspath(project_root)
        self.summary_file = os.path.join(self.project_root, ".tac_project_files.json")
        self.summarizer = FileSummarizer()
        # File extensions supported for Three.js projects
        self.supported_extensions = [
            '.py',               # Python files
            '.js', '.mjs',       # JavaScript files
            '.ts', '.tsx',       # TypeScript files
            '.json',             # JSON files for models/configurations
            '.html',             # HTML files for web pages
            '.glsl', '.vert', '.frag', '.shader',  # GLSL shader files
            # C and C++ files
            '.c', '.cc', '.cpp', '.cxx',           # C/C++ source files
            '.h', '.hh', '.hpp', '.hxx',           # C/C++ header files
            '.inl', '.tpp', '.ipp'                 # C++ inline/template implementation files
        ]
        # Load gitignore patterns only if enabled in config
        self.gitignore_patterns = self._load_gitignore_patterns() if config.general.respect_gitignore else []
        
    def _load_gitignore_patterns(self) -> List[str]:
        """Load and parse .gitignore patterns"""
        gitignore_path = os.path.join(self.project_root, '.gitignore')
        patterns = []
        
        if os.path.exists(gitignore_path):
            try:
                with open(gitignore_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        # Skip empty lines and comments
                        if line and not line.startswith('#'):
                            patterns.append(line)
            except Exception as e:
                logger.warning(f"Error reading .gitignore: {str(e)}")
        
        return patterns
    
    def _is_ignored_by_gitignore(self, path: str) -> bool:
        """Check if a path is ignored by gitignore patterns"""
        if not config.general.respect_gitignore or not self.gitignore_patterns:
            return False
            
        # Convert to relative path from project root
        rel_path = os.path.relpath(path, self.project_root)
        
        # Handle patterns
        for pattern in self.gitignore_patterns:
            # Handle negation patterns (starting with !)
            if pattern.startswith('!'):
                continue  # Skip negation for now (basic implementation)
            
            # Handle directory-only patterns (ending with /)
            if pattern.endswith('/'):
                pattern = pattern[:-1]
                if os.path.isdir(path) and fnmatch.fnmatch(rel_path, pattern):
                    return True
                # Also check if any parent directory matches
                parent_path = rel_path
                while parent_path:
                    if fnmatch.fnmatch(os.path.basename(parent_path), pattern):
                        return True
                    parent_path = os.path.dirname(parent_path)
                    if not parent_path or parent_path == '.':
                        break
            else:
                # Handle file patterns
                if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(os.path.basename(rel_path), pattern):
                    return True
                # Check if any parent directory matches the pattern
                parent_path = rel_path
                while parent_path:
                    if fnmatch.fnmatch(parent_path, pattern):
                        return True
                    parent_path = os.path.dirname(parent_path)
                    if not parent_path or parent_path == '.':
                        break
        
        return False
    
    def _compute_file_hash(self, file_path: str) -> str:
        """Compute SHA-256 hash of file contents"""
        with open(file_path, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()
    
    def _load_existing_summaries(self) -> Dict:
        """Load existing summaries from JSON file"""
        if os.path.exists(self.summary_file):
            try:
                with open(self.summary_file, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return {"files": {}, "last_updated": None}
        return {"files": {}, "last_updated": None}
    
    def _save_summaries(self, data: Dict):
        """Save summaries to JSON file"""
        with open(self.summary_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def update_summaries(self, exclusions: Optional[List[str]] = None, exclude_dot_files: bool = True, progress_callback=None) -> Dict:
        """
        Update summaries for all supported files in the project.
        Only updates files that have changed since last run.
        Saves progress after each file.
        
        Args:
            exclusions: List of directory names to exclude
            exclude_dot_files: Whether to exclude files/dirs starting with '.'
            progress_callback: Optional callback function to report progress (total, processed, stage)
            
        Returns:
            Dict containing stats about the update
        """
        if exclusions is None:
            exclusions = [".git", "__pycache__", "venv", "env", "build", "node_modules", "dist"]
            
        # Load existing data
        data = self._load_existing_summaries()
        existing_files = set(data["files"].keys())
        current_files = set()
        stats = {"added": 0, "updated": 0, "unchanged": 0, "removed": 0}
        
        # First pass: collect all supported files
        all_files = []
        for root, dirs, files in os.walk(self.project_root):
            # Filter directories: exclude specified, dot-files, ignore_paths from config, and gitignore
            dirs[:] = [d for d in dirs 
                      if d not in exclusions 
                      and d not in config.general.ignore_paths 
                      and not (exclude_dot_files and d.startswith('.'))
                      and not self._is_ignored_by_gitignore(os.path.join(root, d))]
            
            for file in files:
                # Check if file has a supported extension
                if any(file.endswith(ext) for ext in self.supported_extensions) and \
                   not file.startswith('.#') and \
                   not (exclude_dot_files and file.startswith('.')):
                    
                    file_path = os.path.join(root, file)
                    abs_file_path = os.path.abspath(file_path)
                    real_path = os.path.realpath(abs_file_path)
                    
                    # Skip if ignored by gitignore
                    if self._is_ignored_by_gitignore(file_path):
                        continue
                    
                    if real_path.startswith(self.project_root):  # Only include files in project
                        all_files.append((file_path, real_path))

        files_to_process = []
        
        # Report initial discovery progress
        if progress_callback:
            progress_callback(len(all_files), 0, "discovery")
        
        # Check which files need processing
        for i, (file_path, real_path) in enumerate(all_files):
            rel_path = os.path.relpath(file_path, self.project_root)
            current_files.add(rel_path)
            
            # Report progress of file checking
            if progress_callback and i % 10 == 0:  # Update progress every 10 files to avoid too many updates
                progress_callback(len(all_files), i, "checking")
            
            # Get file info
            file_size = os.path.getsize(file_path)
            current_hash = self._compute_file_hash(file_path)
            
            # Check if file needs updating
            file_entry = data["files"].get(rel_path, {})
            if not file_entry or file_entry.get("hash") != current_hash:
                files_to_process.append((file_path, rel_path, current_hash, file_size))
            else:
                stats["unchanged"] += 1
                
        if files_to_process:
            logger.info(f"Indexing {len(files_to_process)} files ({len(all_files) - len(files_to_process)} unchanged)")
        
        # Report status before processing
        if progress_callback:
            progress_callback(len(files_to_process), 0, "processing")
        
        # Process files that need updating with tqdm progress bar
        lock = threading.Lock()
        def process_file(args):
            file_path, rel_path, current_hash, file_size = args
            last_modified = datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat()
            analysis = self.summarizer.analyze_file(file_path)
            with lock:
                if not analysis["error"]:
                    data["files"][rel_path] = {
                        "hash": current_hash,
                        "size": file_size,
                        "last_modified": last_modified,
                        "summary_high_level": analysis["summary_high_level"],
                        "summary_detailed": analysis["summary_detailed"]
                    }
                    if rel_path in existing_files:
                        stats["updated"] += 1
                    else:
                        stats["added"] += 1
                else:
                    data["files"][rel_path] = {
                        "hash": current_hash,
                        "size": file_size,
                        "last_modified": last_modified,
                        "error": analysis["error"]
                    }
                    logger.warning(f"Error analyzing {rel_path}: {analysis['error']}")
                data["last_updated"] = datetime.now().isoformat()
                self._save_summaries(data)
            return rel_path
        if files_to_process:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                pbar = tqdm(executor.map(process_file, files_to_process), total=len(files_to_process), desc="Indexing files", unit="file")
                for i, rel_path in enumerate(pbar):
                    pbar.set_description(f"Indexing {rel_path}")
                    if progress_callback:
                        progress_callback(len(files_to_process), i+1, "processing")
        
        # Find and remove any files that no longer exist
        removed_files = existing_files - current_files
        if removed_files:
            # Report final cleanup stage
            if progress_callback:
                progress_callback(len(removed_files), 0, "cleanup")
                
            for i, file in enumerate(removed_files):
                del data["files"][file]
                stats["removed"] += 1
                
                # Report cleanup progress
                if progress_callback:
                    progress_callback(len(removed_files), i+1, "cleanup")
            
            # Save final update
            data["last_updated"] = datetime.now().isoformat()
            self._save_summaries(data)
        
        # Report completion
        if progress_callback:
            progress_callback(100, 100, "complete")
            
        # Log final stats
        logger.info(f"Summary update complete: +{stats['added']}, ~{stats['updated']}, -{stats['removed']}, ={stats['unchanged']} files")
        
        return stats
    
    def get_file_summary(self, file_path: str) -> Optional[Dict]:
        """Get summary for a specific file"""
        data = self._load_existing_summaries()
        rel_path = os.path.relpath(file_path, self.project_root)
        return data["files"].get(rel_path)
    
    def get_all_summaries(self) -> Dict:
        """Get all file summaries"""
        return self._load_existing_summaries()

    def get_file_content(self, file_path: str, use_summaries: bool = False) -> str:
        """
        Get file content, either as full content or summary if enabled.
        
        Args:
            file_path: Path to the file
            use_summaries: Whether to use summaries instead of full content
            
        Returns:
            str: File content or summary
        """
        if not use_summaries:
            try:
                with open(file_path, 'r') as f:
                    return f.read()
            except Exception as e:
                logger.warning(f"Error reading file {file_path}: {str(e)}")
                return f"Error reading file: {str(e)}"

        summary = self.get_file_summary(file_path)
        if summary:
            if "error" in summary:
                return f"Error analyzing file: {summary['error']}"
            
            high_level = summary.get("summary_high_level", "")
            detailed = summary.get("summary_detailed", "")
            
            if high_level and detailed:
                return f"High-level summary: {high_level}\n\n{detailed}"
            elif high_level:
                return high_level
            elif "summary" in summary:  # Backward compatibility
                return summary.get("summary", "No summary available")
            
            return "No summary available"
        
        return f"No summary available for {file_path}" 

    def get_codebase_summary(self) -> str:
        """
        Format all file summaries into a string representation.
        Each file's summary is formatted as:
        ###FILE: relative path to file
        contents of summary
        ###END_FILE
        
        Returns:
            str: Formatted string containing all file summaries
        """
        data = self._load_existing_summaries()
        formatted_strings = []
        
        for rel_path, file_info in data["files"].items():
            if "error" in file_info:
                summary = f"Error analyzing file: {file_info['error']}"
            else:
                high_level = file_info.get("summary_high_level", "")
                detailed = file_info.get("summary_detailed", "")
                
                if high_level and detailed:
                    summary = f"High-level summary: {high_level}\n\n{detailed}"
                elif high_level:
                    summary = high_level
                elif "summary" in file_info:  # Backward compatibility
                    summary = file_info.get("summary", "No summary available")
                else:
                    summary = "No summary available"
                
            formatted_strings.append(
                f"###FILE: {rel_path}\n{summary}\n###END_FILE"
            )
        
        return "\n\n".join(formatted_strings)
        
    def refresh_index(self, progress_callback=None) -> Dict:
        """
        Wrapper for update_summaries to maintain compatibility with UI code.
        
        Args:
            progress_callback: Optional callback function to report progress
            
        Returns:
            Dict: Statistics about the update
        """
        return self.update_summaries(progress_callback=progress_callback)
        
    def get_function_location(self, function_name: str) -> Union[str, bool]:
        """
        Check if a function with the given name exists in the codebase.
        
        Args:
            function_name: Name of the function to find
            
        Returns:
            Union[str, bool]: 
                - Returns the relative path of the file containing the function if it exists in exactly one file
                - Returns False if the function doesn't exist or exists in multiple files
        """
        found_locations = []
        
        for root, _, files in os.walk(self.project_root):
            for file in files:
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            tree = ast.parse(f.read(), filename=file_path)
                            for node in ast.walk(tree):
                                if isinstance(node, ast.FunctionDef) and node.name == function_name:
                                    rel_path = os.path.relpath(file_path, self.project_root)
                                    found_locations.append(rel_path)
                    except Exception as e:
                        logger.warning(f"Error parsing {file_path}: {str(e)}")
                        continue
                
                # Search for JavaScript/TypeScript functions for Three.js projects
                elif file.endswith(('.js', '.mjs', '.ts', '.tsx')):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            # Simple pattern matching for JS/TS function definitions
                            # This is a basic implementation - for more robust parsing, 
                            # consider using a JavaScript parser library
                            patterns = [
                                f"function {function_name}\\s*\\(",  # function declaration
                                f"const {function_name}\\s*=\\s*function",  # function expression
                                f"let {function_name}\\s*=\\s*function",
                                f"var {function_name}\\s*=\\s*function",
                                f"const {function_name}\\s*=\\s*\\(",  # arrow function
                                f"let {function_name}\\s*=\\s*\\(",
                                f"var {function_name}\\s*=\\s*\\(",
                                f"{function_name}\\s*=\\s*function",   # object method
                                f"{function_name}\\s*\\([^)]*\\)\\s*\\{{"  # method shorthand
                            ]
                            for pattern in patterns:
                                if re.search(pattern, content):
                                    rel_path = os.path.relpath(file_path, self.project_root)
                                    found_locations.append(rel_path)
                                    break
                    except Exception as e:
                        logger.warning(f"Error parsing {file_path}: {str(e)}")
                        continue
        
        if len(found_locations) == 1:
            return found_locations[0]  # Return the relative path of the file containing the function
        else:
            return False  # Return False if function doesn't exist or exists in multiple files





if __name__ == "__main__":
    # Example usage of ProjectFiles
    
    # Initialize ProjectFiles with current directory
    project_files = ProjectFiles(".")
    logger.info(project_files.get_codebase_summary())
    # import pdb; pdb.set_trace()

