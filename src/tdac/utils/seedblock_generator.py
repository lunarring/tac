from tdac.utils.file_gatherer import gather_python_files

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
    Generate a seedblock YAML template from a directory of Python files.
    
    Args:
        directory: Path to the directory containing Python files
        template_type: The type of template to use (e.g., "refactor", "default")
    
    Returns:
        A string containing the seedblock YAML template
    """
    # Gather file contents using existing file gatherer
    file_content = gather_python_files(directory)
    
    # Get the template configuration
    template_config = get_seedblock_template(template_type)
    
    # Generate the seedblock template
    template = f"""We have the following codebase: 
{file_content}
    
I want you to generate an instruction block (called seedblock) which is the input for a coding agent. The block has a very specific format that I need you to adhere to precisely, here is the format. For the text of each of the points, don't use line breaks, just write it all in one line.

--------------------

seedblock:
  instructions: {template_config["instructions"]}

task:
  specification: given the entire codebase and the seedblock instruction, here we describe the task at hand very precisely. However we are not implementing the task here and we are not describing exactly HOW the code needs to be changed. You can come up with a proposal of how this could be achieved, but we do NOT need to implement it. Given your understanding of the seed block instructions and the codebase, you come up with a proposal for this!

test: 
  specification: given the entire codebase and the seedblock instruction, here we describe the test specification for the task at hand. We are aiming to just write ONE single test, which is able to infer whether the functionality update in the main code has been implemented correctly or not. Thus, the goal is is figure out if the task has been implemented correctly. Critically, the test needs to be fulfillable. We do NOT need to test anything else than the NEW functionality given the task specification. The rest of the code will be tested by other means anyways, so don't mention it. However, if you are forseeing that the new test will clash with an existing test, because maybe code will be replaced, then mention it in the field 'replacements'.
  data: describe in detail the input data for the test and the expected outcome. Use the provided codebase as a reference. The more detail the better, make it as concrete as possible.
  replacements: list of tests that need to be replaced by the new test. use relative file paths as given in the codebase. leave empty if no replacements are needed.

write_files: list of files that may need to be written for the task. use relative file paths as given in the codebase.
  
context_files: list of files that need to be read for context in order to implement the task and as background information for the test. use relative file paths as given in the codebase.

--------------------

Please analyze the codebase and provide a seedblock YAML that addresses this task: {template_config["instructions"] if template_config["instructions"] else "Describe your task here"}"""
    return template 