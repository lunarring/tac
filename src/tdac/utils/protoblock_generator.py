from tdac.utils.file_gatherer import gather_python_files

def generate_protoblock(directory: str) -> str:
    """
    Generate a protoblock YAML template from a directory of Python files.
    
    Args:
        directory: Path to the directory containing Python files
    
    Returns:
        A string containing the protoblock YAML template
    """
    # Gather file contents using existing file gatherer
    file_content = gather_python_files(directory)
    
    # Generate the protoblock template
    template = f"""We have the following codebase: 
{file_content}
    
I want you to generate an instruction block (called protoblock) which is the input for a coding agent. The block has a very specific format that I need you to adhere to precisely, here is the format. For the text of each of the points, don't use line breaks, just write it all in one line.

--------------------

seedblock:
  instructions: instruction of the change in the code that was requested. this is just for reference, and it is an exact copy of the instructions that were received for creating this protoblock

task:
  specification: given the entire codebase and the seedblock instruction, here we describe the task at hand very precisely. However we are not implementing the task here and we are not describing exactly HOW the code needs to be changed. You can come up with a proposal of how this could be achieved, but we do NOT need to implement it. Given your understanding of the seed block instructions and the codebase, you come up with a proposal for this!
  write_files: list of files that may need to be written for the task. use relative file paths as given in the codebase. Don't list test files here.

test: 
  specification: given the entire codebase and the seedblock instruction, here we describe the test specification for the task at hand. We are aiming to just write ONE single test, which is able to infer whether the functionality update in the main code has been implemented correctly or not. Thus, the goal is is figure out if the task has been implemented correctly. Critically, the test needs to be fulfillable. We do NOT need to test anything else than the NEW functionality given the task specification. The rest of the code will be tested by other means anyways, so don't mention it. However, if you are forseeing that the new test will clash with an existing test, because maybe code will be replaced, then mention it in the field 'replacements'.
  data: describe in detail the input data for the test and the expected outcome. Use the provided codebase as a reference. The more detail the better, make it as concrete as possible.
  replacements: list of tests that need to be replaced by the new test. use relative file paths as given in the codebase. leave empty if no replacements are needed.

context_files: list of files that need to be read for context in order to implement the task and as background information for the test. use relative file paths as given in the codebase.

--------------------

Now we have a following task, i.e. new functionality to implement. Answer in the yaml file directly and below it provide me a brief high level comment statement and your assertion how easy it is to implement that change! Here it is: """
    return template 