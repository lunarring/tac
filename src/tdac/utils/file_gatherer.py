import os
from datetime import datetime

def gather_python_files(directory, formatting_options=None, exclusions=None, exclude_dot_files=True):
    if formatting_options is None:
        formatting_options = {"header": "## File: ", "separator": "\n---\n", "use_code_fences": True}
    if exclusions is None:
        exclusions = [".git", "__pycache__"]

    # Size thresholds in bytes (100KB total, showing 40KB from start and end)
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

                # Gather file content
                with open(file_path, 'r') as f:
                    content = f.read()

                # Format file content
                header = f"{formatting_options['header']}{file}"
                if formatting_options['use_code_fences']:
                    content = f"```python\n{content}\n```"
                
                file_size = os.path.getsize(file_path)
                file_info = f"Size: {file_size} bytes, Last Modified: {datetime.fromtimestamp(os.path.getmtime(file_path))}"
                
                # Handle large files by summarizing
                if file_size > MAX_FILE_SIZE:
                    skipped_bytes = file_size - (2 * CHUNK_SIZE)
                    content = (
                        f"```python\n"
                        f"# First {CHUNK_SIZE//1024}KB of file:\n"
                        f"{content[3:CHUNK_SIZE+3]}\n\n"  # Skip first 3 chars which are ```
                        f"# ... [{skipped_bytes//1024}KB truncated] ...\n\n"
                        f"# Last {CHUNK_SIZE//1024}KB of file:\n"
                        f"{content[-CHUNK_SIZE-4:-4]}\n"  # Skip last 4 chars which are \n```
                        f"```"
                    )
                
                file_contents.append(f"{header}\n{file_info}\n{content}")

    if not file_contents:
        return "No Python files found."

    # Combine directory tree and file contents
    result = "\n".join(directory_tree) + formatting_options['separator'] + "\n".join(file_contents)
    return result
