import os
from datetime import datetime
from tac.utils.project_files import ProjectFiles
import sys

def cli_gather_files(directory, formatting_options, exclusions, exclude_dot_files=True):
    """
    Gather files from directory and load file contents without extra summarization.
    
    Args:
        directory: Directory to scan.
        formatting_options: Dictionary with formatting options.
        exclusions: List of directories to exclude.
        exclude_dot_files: Whether to exclude files/directories starting with a dot.
        
    Returns:
        Dictionary with file paths as keys and file contents as values.
    """
    MAX_FILE_SIZE = 100 * 1024  
    CHUNK_SIZE = 40 * 1024

    # Same extensions as in ProjectFiles
    SUPPORTED_EXTENSIONS = [
        '.py',               # Python files
        '.js', '.mjs',       # JavaScript files
        '.ts', '.tsx',       # TypeScript files
        '.json',             # JSON files for models/configurations
        '.html',             # HTML files for web pages
        '.glsl', '.vert', '.frag', '.shader'  # GLSL shader files
    ]

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
        # Add the root folder name only if it's not the base directory
        if rel_root == '.':
            directory_tree.append(f"{os.path.basename(root)}/")
        else:
            directory_tree.append(f"{indent}{os.path.basename(root)}/")

        for file in files:
            # Check if file has a supported extension
            if any(file.endswith(ext) for ext in SUPPORTED_EXTENSIONS) and not file.startswith('.#') and not (exclude_dot_files and file.startswith('.')):
                file_path = os.path.join(root, file)
                abs_file_path = os.path.abspath(file_path)
                real_path = os.path.realpath(abs_file_path)  # Resolve any symlinks
                
                # Skip if we've seen this file before (either directly or through a symlink)
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
                    content = f"```{os.path.splitext(file)[1][1:] or 'text'}\n{content}\n```"
                
                file_contents.append(f"{header}\n{file_info}\n{content}")

    if not file_contents:
        return "No supported files found."

    return "\n".join(directory_tree) + formatting_options['separator'] + "\n".join(file_contents)

def gather_files_command(args):
    """Handle the gather command execution"""
    if args.summarize:
        project_files = ProjectFiles(args.directory)
        
        # Update summaries and show stats
        exclusions = args.exclusions.split(',') if args.exclusions else None
        stats = project_files.update_summaries(exclusions, not args.include_dot_files)
        
        print(f"\nSummary update stats:")
        print(f"Added: {stats['added']} files")
        print(f"Updated: {stats['updated']} files")
        print(f"Unchanged: {stats['unchanged']} files")
        print(f"Removed: {stats['removed']} files")
        
        # If it's a single file, show its summary
        if os.path.isfile(args.directory) and args.directory.endswith('.py'):
            summary = project_files.get_file_summary(args.directory)
            if summary:
                if "error" in summary:
                    print(f"\nError analyzing file: {summary['error']}")
                else:
                    print(f"\n## File: {os.path.basename(args.directory)}")
                    print(f"Size: {summary['size']} bytes, Last Modified: {datetime.fromtimestamp(os.path.getmtime(args.directory))}")
                    print(f"\n```python\n{summary['summary']}\n```")
        else:
            # Show all summaries
            data = project_files.get_all_summaries()
            print(f"\nLast updated: {data['last_updated']}\n")
            
            for file_path, info in sorted(data["files"].items()):
                if "error" in info:
                    print(f"## File: {file_path}")
                    print(f"Size: {info['size']} bytes, Last Modified: {info['last_modified']}")
                    print(f"Error: {info['error']}\n")
                else:
                    print(f"## File: {file_path}")
                    print(f"Size: {info['size']} bytes, Last Modified: {info['last_modified']}")
                    print(f"\n```python\n{info['summary']}\n```\n")
    else:
        formatting_options = {
            "header": args.header,
            "separator": args.separator,
            "use_code_fences": args.code_fences
        }
        if os.path.isfile(args.directory) and args.directory.endswith('.py'):
            # Single file content
            with open(args.directory, 'r') as f:
                content = f.read()
            file_size = os.path.getsize(args.directory)
            file_info = f"Size: {file_size} bytes, Last Modified: {datetime.fromtimestamp(os.path.getmtime(args.directory))}"
            if formatting_options["use_code_fences"]:
                content = f"```python\n{content}\n```"
            print(f"{formatting_options['header']}{os.path.basename(args.directory)}\n{file_info}\n{content}")
        else:
            # Directory content
            if not os.path.isdir(args.directory):
                print(f"Error: {args.directory} is not a directory or Python file")
                sys.exit(1)
            exclusions = args.exclusions.split(',') if args.exclusions else None
            result = cli_gather_files(args.directory, formatting_options, exclusions)
            print(result) 