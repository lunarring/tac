import os
from datetime import datetime
from tac.core.config import config

def gather_python_files(directory, formatting_options=None, exclusions=None, exclude_dot_files=True):
    """
    Gather Python files from directory and load file contents without extra summarization.
    
    Args:
        directory: Directory to scan.
        formatting_options: Options for formatting output.
        exclusions: List of directories to exclude.
        exclude_dot_files: Whether to exclude files and directories starting with a dot.
        
    Returns:
        str: Formatted output of file tree and contents.
    """
    if formatting_options is None:
        formatting_options = {"header": "## File: ", "separator": "\n---\n", "use_code_fences": True}
    if exclusions is None:
        exclusions = [".git", "__pycache__", "build"]

    MAX_FILE_SIZE = 100 * 1024  
    CHUNK_SIZE = 40 * 1024

    directory_tree = []
    file_contents = []
    seen_files = set()  # Track unique files by their absolute path

    directory = str(directory)  # Ensure directory is a string
    abs_directory = os.path.abspath(directory)  # Get absolute path of base directory

    for root, dirs, files in os.walk(directory):
        # Exclude specified directories and optionally dot directories
        dirs[:] = [d for d in dirs if d not in exclusions and not (exclude_dot_files and d.startswith('.'))]
        rel_root = os.path.relpath(root, directory)
        level = root.replace(directory, '').count(os.sep)
        indent = ' ' * 4 * level
        if rel_root == '.':
            directory_tree.append(f"{os.path.basename(root)}/")
        else:
            directory_tree.append(f"{indent}{os.path.basename(root)}/")

        for file in files:
            if file.endswith('.py') and not file.startswith('.#') and not (exclude_dot_files and file.startswith('.')):
                file_path = os.path.join(root, file)
                abs_file_path = os.path.abspath(file_path)
                real_path = os.path.realpath(abs_file_path)  # Resolve any symlinks
                
                # Skip if we've seen this file before
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

                # Load file content
                if file_size > MAX_FILE_SIZE:
                    with open(file_path, 'r') as f:
                        content = f.read()
                    content = (
                        f"# First {CHUNK_SIZE//1024}KB of file:\n"
                        f"{content[:CHUNK_SIZE]}\n\n"
                        f"# ... [{(file_size - 2*CHUNK_SIZE)//1024}KB truncated] ...\n\n"
                        f"# Last {CHUNK_SIZE//1024}KB of file:\n"
                        f"{content[-CHUNK_SIZE:]}"
                    )
                else:
                    with open(file_path, 'r') as f:
                        content = f.read()

                # Format content
                header = f"{formatting_options['header']}{os.path.relpath(file_path, directory)}"
                if formatting_options.get('use_code_fences'):
                    content = f"```python\n{content}\n```"
                
                file_contents.append(f"{header}\n{file_info}\n{content}")

    if not file_contents:
        return "No Python files found."

    return "\n".join(directory_tree) + formatting_options['separator'] + "\n".join(file_contents)