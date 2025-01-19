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
    
I want you to generate an instruction block for a programming agent. The block has a very specific format that I need you to adhere to, here is an example:

project:
  name: real_time_stats_update
  project_dir: /Users/jjj/git/piano_trainer

block:
  function_name: update_statistics
  file_path: src/piano_trainer.py
  task_description: |
    Enhance the system so that performance metrics are recalculated immediately 
    after each individual tone is processed. Previously, these metrics were 
    calculated either only at the conclusion of the entire process or once 
    for the entire set of tones. Now, each time a tone is received and processed, 
    the relevant logic should be triggered to generate and store updated metrics 
    on the spot. Displaying or reporting these metrics is not required at this time.

  test_specification: |
    Verification will ensure that for each tone received, the update process 
    for performance metrics is executed immediately. Key points include:
      1) Updates occur right after each tone—no deferrals until the full set is processed.
      2) The process must accept structured information about each tone (e.g., 
         properties like pitch or duration).
      3) The continuous accumulation of metrics should be validated at each step.

  test_data_generation: |
    Test data will consist of a series of tones, each defined by essential properties 
    such as pitch and duration. For instance:
      - pitch = 60, duration = 100
      - pitch = 62, duration = 150
      - pitch = 64, duration = 200

    Each tone in the series is then processed, and the verification confirms that 
    metrics are updated immediately and accurately for each tone. 
    The timing and correctness of these updates are the main focus.

———————————————

Crucially, you need to take care of the following with the highest precision possible:
- have the correct file_path for the files that need to be modified
- this is the only place to mention python files 
- don't exactly describe the functions or classes and how they need to be changed, just describe the task at hand very precisely, given the codebase below. the more precise you can describe the task, the better!
- describe the tests very precisely. they need to be able to test whether the task update has been implemented correctly or not. try to make simple tests, keep it easy and modular.
- we do NOT need to test anything else than the NEW functionality. the rest of the code will be tested by other means anyways, so don't mention it.

———————————————

Now we have the following task at hand, below it I will then provide you the codebase. Answer in the yaml file directly and below it provide me a brief high level comment statement and your assertion how easy it is to implement that change!"""
    return template 