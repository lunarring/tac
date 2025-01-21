from tdac.utils.file_gatherer import gather_python_files
import json
import time
import random
import string

# Predefined templates for different seed types
SEED_TEMPLATES = {
    "refactor": {
        "instructions": "Analyze the entire codebase to identify areas of redundancy and complexity, focusing on improving maintainability. Remove or refactor duplicate code segments, ensuring that any repetitive logic is consolidated into reusable functions or modules. Improve naming conventions, code structure, and documentation to enhance readability and consistency across the project. Address code smells by applying relevant design patterns and best practices, including principles like DRY (Don't Repeat Yourself). Finally, verify all changes through comprehensive testing and update any related documentation to maintain clarity for future contributors.",
        "description": "Generate a refactoring seed"
    },
    "error": {
        "instructions": "An error occurred while running the code. Analyze the error message, trace through the codebase, and determine the root cause of the issue. Focus on ONE specific error and propose a solution.",
        "description": "Generate an error analysis seed"
    },
    "test": {
        "instructions": "We want to add comprehensive tests to verify the existing functionality. Do NOT modify any code EXCEPT for the test files. We want to have maximum coverage of the codebase. Thereofore you think through which would be a good test to add! Focus solely on creating this one robust, maintainable tests that document and verify the current behavior.",
        "description": "Generate a testing seed"
    },
    "default": {
        "instructions": "",
        "description": "Generate a standard seed"
    }
}

def get_seed_template(template_type: str = "default") -> dict:
    """Get a predefined seed template.
    
    Args:
        template_type: The type of template to use (e.g., "refactor", "default")
    
    Returns:
        A dictionary containing the template configuration
    """
    return SEED_TEMPLATES.get(template_type, SEED_TEMPLATES["default"])

def generate_seed(directory: str, template_type: str = "default") -> str:
    """
    Generate a seed JSON template from a directory of Python files.
    
    Args:
        directory: Path to the directory containing Python files
        template_type: The type of template to use (e.g., "refactor", "default")
    
    Returns:
        A string containing the seed JSON template
    """
    # Gather file contents using existing file gatherer
    file_content = gather_python_files(directory)
    
    # Get the template configuration
    template_config = get_seed_template(template_type)
    
    # Generate simple 6-character unique identifier
    unique_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    
    # Generate the seed template
    template = {
        "id": unique_id,  # Add unique identifier
        "type": template_type,  # Add template type
        "description": f"""We have the following codebase:
{file_content}

I want you to generate an instruction block (called seed) which is the input for a coding agent. The block has a very specific format that I need you to adhere to precisely. Write in very concise language, and write in a tone of giving direct and precise orders. The response should be a valid JSON object with the following structure:

{{
    "seed": {{
        "instructions": "Brief instructions for the task"
    }},
    "task": {{
        "specification": "Detailed task specification"
    }},
    "test": {{
        "specification": "Test specification",
        "data": "Test data and expected outcomes",
        "replacements": ["file1.py", "file2.py"]
    }},
    "write_files": ["file1.py", "file2.py"],
    "context_files": ["context1.py", "context2.py"],
    "commit_message": "TDAC: Brief commit message"
}}

Please analyze the codebase and provide a seed that addresses this task: {template_config["instructions"] if template_config["instructions"] else "Describe your task here"}"""
    }
    
    return json.dumps(template, indent=2) 