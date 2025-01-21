from tdac.utils.file_gatherer import gather_python_files
import json

# Predefined templates for different seedblock types
SEEDBLOCK_TEMPLATES = {
    "refactor": {
        "instructions": "We want to refactor the code because it is ugly and not very well done. Pick ONE single item for refactoring that seems most pressing.",
        "description": "Generate a refactoring seedblock"
    },
    "error": {
        "instructions": "An error occurred while running the code. Analyze the error message, trace through the codebase, and determine the root cause of the issue. Focus on ONE specific error and propose a solution.",
        "description": "Generate an error analysis seedblock"
    },
    "test": {
        "instructions": "We want to add comprehensive tests to verify the existing functionality. Do NOT modify any production code - focus solely on creating robust, maintainable tests that document and verify the current behavior. Pick ONE specific component or function to test thoroughly.",
        "description": "Generate a testing seedblock"
    },
    "default": {
        "instructions": "",
        "description": "Generate a standard seedblock"
    }
}

def get_seedblock_template(template_type: str = "default") -> dict:
    """Get a predefined seedblock template.
    
    Args:
        template_type: The type of template to use (e.g., "refactor", "default")
    
    Returns:
        A dictionary containing the template configuration
    """
    return SEEDBLOCK_TEMPLATES.get(template_type, SEEDBLOCK_TEMPLATES["default"])

def generate_seedblock(directory: str, template_type: str = "default") -> str:
    """
    Generate a seedblock JSON template from a directory of Python files.
    
    Args:
        directory: Path to the directory containing Python files
        template_type: The type of template to use (e.g., "refactor", "default")
    
    Returns:
        A string containing the seedblock JSON template
    """
    # Gather file contents using existing file gatherer
    file_content = gather_python_files(directory)
    
    # Get the template configuration
    template_config = get_seedblock_template(template_type)
    
    # Generate the seedblock template
    template = {
        "description": f"""We have the following codebase:
{file_content}

I want you to generate an instruction block (called seedblock) which is the input for a coding agent. The block has a very specific format that I need you to adhere to precisely. Write in very concise language, and write in a tone of giving direct and precise orders. The response should be a valid JSON object with the following structure:

{{
    "seedblock": {{
        "instructions": "Brief instructions for the task"
    }},
    "task": {{
        "specification": "Detailed task specification"
    }},
    "test": {{
        "specification": "Test specification",
        "data": "Test data and expected outcomes",
        "replacements": ["list", "of", "files", "to", "replace"]
    }},
    "write_files": ["list", "of", "files", "to", "write"],
    "context_files": ["list", "of", "files", "for", "context"],
    "commit_message": "TDAC: Brief commit message"
}}

Please analyze the codebase and provide a seedblock that addresses this task: {template_config["instructions"] if template_config["instructions"] else "Describe your task here"}"""
    }
    
    return json.dumps(template, indent=2) 