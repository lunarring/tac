import os
import json
import hashlib
from datetime import datetime
from typing import Dict, List, Optional
from tac.utils.file_summarizer import FileSummarizer
from tac.core.config import config
import logging
from tqdm import tqdm
import ast

logger = logging.getLogger(__name__)

class ProjectFiles:
    """Manages project-wide file summaries and tracking"""
    
    def __init__(self, project_root: str = "."):
        self.project_root = os.path.abspath(project_root)
        self.summary_file = os.path.join(self.project_root, ".tac_project_files.json")
        self.summarizer = FileSummarizer()
        
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
    
    def update_summaries(self, exclusions: Optional[List[str]] = None, exclude_dot_files: bool = True) -> Dict:
        """
        Update summaries for all Python files in the project.
        Only updates files that have changed since last run.
        Saves progress after each file.
        
        Args:
            exclusions: List of directory names to exclude
            exclude_dot_files: Whether to exclude files/dirs starting with '.'
            
        Returns:
            Dict containing stats about the update
        """
        if exclusions is None:
            exclusions = [".git", "__pycache__", "venv", "env", "build"]
            
        # Load existing data
        data = self._load_existing_summaries()
        existing_files = set(data["files"].keys())
        current_files = set()
        stats = {"added": 0, "updated": 0, "unchanged": 0, "removed": 0}
        
        # First pass: collect all Python files
        all_files = []
        for root, dirs, files in os.walk(self.project_root):
            # Filter directories: exclude specified, dot-files, and ignore_paths from config
            dirs[:] = [d for d in dirs if d not in exclusions and d not in config.general.ignore_paths and not (exclude_dot_files and d.startswith('.'))]
            
            for file in files:
                if (file.endswith('.py') and 
                    not file.startswith('.#') and 
                    not (exclude_dot_files and file.startswith('.'))):
                    
                    file_path = os.path.join(root, file)
                    abs_file_path = os.path.abspath(file_path)
                    real_path = os.path.realpath(abs_file_path)
                    
                    if real_path.startswith(self.project_root):  # Only include files in project
                        all_files.append((file_path, real_path))

        files_to_process = []
        
        # Check which files need processing
        for file_path, real_path in all_files:
            rel_path = os.path.relpath(file_path, self.project_root)
            current_files.add(rel_path)
            
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
            logger.info(f"Processing {len(files_to_process)} files ({len(all_files) - len(files_to_process)} unchanged)")
        
        # Process files that need updating with tqdm progress bar
        pbar = tqdm(files_to_process, desc="Analyzing files", unit="file")
        for file_path, rel_path, current_hash, file_size in pbar:
            pbar.set_description(f"Analyzing {rel_path}")
            last_modified = datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat()
            
            # Analyze file
            analysis = self.summarizer.analyze_file(file_path)
            if not analysis["error"]:
                # Store the summary directly since it's now a string
                data["files"][rel_path] = {
                    "hash": current_hash,
                    "size": file_size,
                    "last_modified": last_modified,
                    "summary": analysis["content"]
                }
                
                if rel_path in existing_files:
                    stats["updated"] += 1
                else:
                    stats["added"] += 1
            else:
                # Keep track of files we couldn't analyze
                data["files"][rel_path] = {
                    "hash": current_hash,
                    "size": file_size,
                    "last_modified": last_modified,
                    "error": analysis["error"]
                }
                logger.warning(f"Error analyzing {rel_path}: {analysis['error']}")
            
            # Save after each file
            data["last_updated"] = datetime.now().isoformat()
            self._save_summaries(data)
        
        # Find and remove any files that no longer exist
        removed_files = existing_files - current_files
        if removed_files:
            for file in removed_files:
                del data["files"][file]
                stats["removed"] += 1
            
            # Save final update
            data["last_updated"] = datetime.now().isoformat()
            self._save_summaries(data)
        
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
            return summary.get("summary", "No summary available")
        
        return f"No summary available for {file_path}" 

    def get_codebase_summary(self) -> str:
        """
        Format all file summaries into a string representation.
        Each file's summary is formatted as:
        ###FILE: <full path to file>
        contents of summary
        ###END_FILE
        
        Returns:
            str: Formatted string containing all file summaries
        """
        data = self._load_existing_summaries()
        formatted_strings = []
        
        for rel_path, file_info in data["files"].items():
            full_path = os.path.abspath(os.path.join(self.project_root, rel_path))
            summary = file_info.get("summary", "No summary available")
            if "error" in file_info:
                summary = f"Error analyzing file: {file_info['error']}"
                
            formatted_strings.append(
                f"###FILE: {full_path}\n{summary}\n###END_FILE"
            )
        
        return "\n\n".join(formatted_strings)





if __name__ == "__main__":
    # Example usage of ProjectFiles
    
    # Initialize ProjectFiles with current directory
    project_files = ProjectFiles(".")
    print(project_files.get_codebase_summary())
    # import pdb; pdb.set_trace()

