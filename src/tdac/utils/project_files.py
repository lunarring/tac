import os
import json
import hashlib
from datetime import datetime
from typing import Dict, List, Optional
from tdac.utils.file_summarizer import FileSummarizer
import logging

logger = logging.getLogger(__name__)

class ProjectFiles:
    """Manages project-wide file summaries and tracking"""
    
    def __init__(self, project_root: str = "."):
        self.project_root = os.path.abspath(project_root)
        self.summary_file = os.path.join(self.project_root, ".tdac_project_files.json")
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
            exclusions = [".git", "__pycache__", "venv", "env"]
            
        # Load existing data
        data = self._load_existing_summaries()
        existing_files = set(data["files"].keys())
        current_files = set()
        stats = {"added": 0, "updated": 0, "unchanged": 0, "removed": 0}
        
        # First pass: collect all Python files
        all_files = []
        for root, dirs, files in os.walk(self.project_root):
            # Filter directories
            dirs[:] = [d for d in dirs if d not in exclusions and not (exclude_dot_files and d.startswith('.'))]
            
            for file in files:
                if (file.endswith('.py') and 
                    not file.startswith('.#') and 
                    not (exclude_dot_files and file.startswith('.'))):
                    
                    file_path = os.path.join(root, file)
                    abs_file_path = os.path.abspath(file_path)
                    real_path = os.path.realpath(abs_file_path)
                    
                    if real_path.startswith(self.project_root):  # Only include files in project
                        all_files.append((file_path, real_path))

        logger.info(f"Found {len(all_files)} Python files in project")
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
            logger.info(f"Need to process {len(files_to_process)} files ({len(all_files) - len(files_to_process)} unchanged)")
        
        # Process files that need updating
        for i, (file_path, rel_path, current_hash, file_size) in enumerate(files_to_process, 1):
            logger.info(f"Processing file {i}/{len(files_to_process)}: {rel_path}")
            
            last_modified = datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat()
            
            # Analyze file
            analysis = self.summarizer._analyze_file(file_path)
            if not analysis["error"]:
                # Format summaries
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
                
                # Update entry
                data["files"][rel_path] = {
                    "hash": current_hash,
                    "size": file_size,
                    "last_modified": last_modified,
                    "summary": summary
                }
                
                if rel_path in existing_files:
                    stats["updated"] += 1
                    logger.info(f"Updated summary for {rel_path}")
                else:
                    stats["added"] += 1
                    logger.info(f"Added summary for {rel_path}")
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
            logger.info(f"Removing {len(removed_files)} files that no longer exist")
            for file in removed_files:
                del data["files"][file]
                stats["removed"] += 1
            
            # Save final update
            data["last_updated"] = datetime.now().isoformat()
            self._save_summaries(data)
        
        # Log final stats
        logger.info(f"Summary update complete:")
        logger.info(f"  Added: {stats['added']} files")
        logger.info(f"  Updated: {stats['updated']} files")
        logger.info(f"  Unchanged: {stats['unchanged']} files")
        logger.info(f"  Removed: {stats['removed']} files")
        
        return stats
    
    def get_file_summary(self, file_path: str) -> Optional[Dict]:
        """Get summary for a specific file"""
        data = self._load_existing_summaries()
        rel_path = os.path.relpath(file_path, self.project_root)
        return data["files"].get(rel_path)
    
    def get_all_summaries(self) -> Dict:
        """Get all file summaries"""
        return self._load_existing_summaries() 