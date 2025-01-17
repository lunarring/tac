import os
from datetime import datetime

def gather_python_files(directory, formatting_options=None, exclusions=None, exclude_dot_files=True):
    if formatting_options is None:
        formatting_options = {"header": "## File: ", "separator": "\n---\n", "use_code_fences": True}
    if exclusions is None:
        exclusions = [".git", "__pycache__"]

    directory_tree = []
    file_contents = []

    directory = str(directory)  # Ensure directory is a string

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
                directory_tree.append(f"{indent}    {file}")

                # Gather file content
                with open(file_path, 'r') as f:
                    content = f.read()

                # Format file content
                header = f"{formatting_options['header']}{file}"
                if formatting_options['use_code_fences']:
                    content = f"```python\n{content}\n```"
                file_info = f"Size: {os.path.getsize(file_path)} bytes, Last Modified: {datetime.fromtimestamp(os.path.getmtime(file_path))}"
                
                # Handle large files by summarizing
                if os.path.getsize(file_path) > 1024:  # Example threshold for large files
                    content = content[:512] + "\n... [Content Truncated] ...\n" + content[-512:]
                
                file_contents.append(f"{header}\n{file_info}\n{content}")

    if not file_contents:
        return "No Python files found."

    # Combine directory tree and file contents
    result = "\n".join(directory_tree) + formatting_options['separator'] + "\n".join(file_contents)
    return result
