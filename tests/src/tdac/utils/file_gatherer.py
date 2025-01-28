import os
from datetime import datetime

def gather_python_files(directory, formatting_options=None, exclusions=None, exclude_dot_files=True, use_summaries=False):
    """
    Gather Python files from a directory, optionally using summaries instead of content.

    Args:
        directory (str): Directory to scan.
        formatting_options (dict, optional): Options for formatting output.
            - header (str): Header prefix for each file.
            - separator (str): Separator between directory tree and file contents.
            - use_code_fences (bool): Whether to wrap file contents in code fences.
        exclusions (list, optional): List of directories to exclude.
        exclude_dot_files (bool, optional): Whether to exclude dot files.
        use_summaries (bool, optional): Whether to use file summaries instead of content.

    Returns:
        str: Formatted output of file tree and contents/summaries.
    """
    if formatting_options is None:
        formatting_options = {
            "header": "## File: ",
            "separator": "\n---\n",
            "use_code_fences": True
        }
    if exclusions is None:
        exclusions = [".git", "__pycache__"]

    # Size thresholds in bytes (100KB total, showing 40KB from start and end)
    MAX_FILE_SIZE = 100 * 1024
    CHUNK_SIZE = 40 * 1024

    directory_tree = []
    file_contents = []
    seen_files = set()  # Track unique files by their absolute path

    # Initialize ProjectFiles if using summaries
    if use_summaries:
        from tdac.utils.project_files import ProjectFiles
        project_files = ProjectFiles()

    directory = str(directory)  # Ensure directory is a string
    abs_directory = os.path.abspath(directory)  # Get absolute path of base directory

    for root, dirs, files in os.walk(directory):
        # Exclude specified directories and optionally dot directories
        dirs[:] = [d for d in dirs if d not in exclusions and not (exclude_dot_files and d.startswith('.'))]

        # Build directory tree
        level = root.replace(directory, '').count(os.sep)
        indent = ' ' * 4 * level
        directory_tree.append(f"{indent}{os.path.basename(root)}/")

        for file in files:
            if (file.endswith('.py') and 
                not file.startswith('.#') and 
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
                directory_tree.append(f"{indent}    {file}")

                # Gather file info
                file_size = os.path.getsize(file_path)
                file_info = f"Size: {file_size} bytes, Last Modified: {datetime.fromtimestamp(os.path.getmtime(file_path))}"

                if use_summaries:
                    # Get or generate summary
                    summary = project_files.get_file_summary(file_path)
                    if not summary:
                        # Generate new summary
                        project_files.update_summaries(exclusions=exclusions)
                        summary = project_files.get_file_summary(file_path)
                    
                    if summary:
                        if "error" in summary:
                            content = f"Error analyzing file: {summary['error']}"
                        else:
                            content = summary["summary"]
                    else:
                        content = "Error: Could not generate summary"
                else:
                    # Use regular file content
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                    except Exception as e:
                        content = f"Error reading file: {e}"
                        file_info += f", Read Error: {e}"

                    if file_size > MAX_FILE_SIZE:
                        content = (
                            f"# First {CHUNK_SIZE//1024}KB of file:\n"
                            f"{content[:CHUNK_SIZE]}\n\n"
                            f"# ... [{(file_size - 2*CHUNK_SIZE)//1024}KB truncated] ...\n\n"
                            f"# Last {CHUNK_SIZE//1024}KB of file:\n"
                            f"{content[-CHUNK_SIZE:]}"
                        )

                # Format content
                header = f"{formatting_options['header']}{os.path.relpath(file_path, directory)}"
                if formatting_options.get('use_code_fences', False):
                    content = f"```python\n{content}\n```"
                
                file_contents.append(f"{header}\n{file_info}\n{content}")

    if not file_contents:
        return "No Python files found."

    return "\n".join(directory_tree) + formatting_options['separator'] + "\n".join(file_contents)
