import json
import uuid
from dataclasses import dataclass
from typing import List, Optional
from tdac.utils.file_gatherer import gather_python_files
from tdac.core.llm import LLMClient, Message

@dataclass
class ProtoBlockSpec:
    """Specification for a protoblock"""
    task_specification: str
    test_specification: str
    test_data: str
    write_files: List[str]
    context_files: List[str]
    commit_message: str
    block_id: str = None

class ProtoBlockFactory:
    """Factory class for creating protoblocks"""
    
    # Predefined templates for different task types
    TEMPLATES = {
        "refactor": {
            "instructions": "Conduct a thorough review of the entire codebase, focusing on one critical area to refactor only the single most problematic issue. For instance, that could mean reorganizing duplicated logic into a shared module or function, clarifying the intent of obscure variable names to make the code more self-explanatory, splitting excessively long methods into smaller, focused pieces, enforcing a consistent formatting style across all files, or adding robust error handling to improve stability. It may also involve consolidating configuration settings to a single source of truth, cleaning out unused or legacy code that no longer serves any purpose, replacing “magic numbers” with clearly named constants, or adopting modern language features to simplify and streamline key operations. The core goal is to address the underlying structural problems in the code so that it becomes easier to read, maintain, and extend—without altering the code’s fundamental functionality. Consolidate  into well-designed, reusable functions or modules. This change is paramount to improving the maintainability and scalability of the codebase. Ensure that each consolidated function is properly named and documented. This targeted effort will lay the groundwork for a cleaner, more efficient project while simplifying collaboration for future contributors."
        },
        "error": {
            "instructions": "An error occurred while running the code. Analyze the error message, trace through the codebase, and determine the root cause of the issue. Focus on ONE specific error and propose a solution."
        },
        "test": {
            "instructions": "We want to add comprehensive tests to verify the existing functionality. Do NOT modify any code EXCEPT for the test files. We want to have maximum coverage of the codebase. Thereofore you think through which would be a good test to add! Focus solely on creating this one robust, maintainable tests that document and verify the current behavior."
        }
    }
    
    def __init__(self):
        self.llm_client = LLMClient()
    
    def get_task_instructions(self, template_type: Optional[str] = None, direct_instructions: Optional[str] = None) -> str:
        """
        Get task-specific instructions either from a template or direct instructions.
        Exactly one of template_type or direct_instructions must be provided.
        
        Args:
            template_type: Type of template to use (refactor, test, error)
            direct_instructions: Direct instructions provided by the user
            
        Returns:
            str: The task-specific instructions to use
            
        Raises:
            ValueError: If neither or both arguments are provided, or if template type is invalid
        """
        if direct_instructions is not None and template_type is not None:
            raise ValueError("Cannot provide both template_type and direct_instructions")
            
        if direct_instructions is not None:
            return direct_instructions
            
        if template_type is None:
            raise ValueError("Must provide either template_type or direct_instructions")
            
        if template_type not in self.TEMPLATES:
            raise ValueError(f"Invalid template type: {template_type}. Must be one of: {', '.join(self.TEMPLATES.keys())}")
            
        return self.TEMPLATES[template_type]["instructions"]
    
    def get_seed_instructions(self, codebase: str, task_instructions: str) -> str:
        """
        Generate complete seed instructions by combining codebase analysis with task instructions.
        
        Args:
            codebase: The codebase content to analyze (result of gather_python_files)
            task_instructions: The specific task instructions to use
            
        Returns:
            str: Complete seed instructions for the LLM
        """
        return f"""We have the following codebase:
{codebase}

I want you to generate instructions which are the input for a coding agent. The instructions have a very specific format that I need you to adhere to precisely. Write in very concise language, and write in a tone of giving direct and precise orders. The response should be a valid JSON object with the following structure:

{{
    "task": {{
        "specification": "Given the entire codebase and the instructions, here we describe the task at hand very precisely. However we are not implementing the task here and we are not describing exactly HOW the code needs to be changed. You can come up with a proposal of how this could be achieved, but we do NOT need to implement it. Given your understanding of the seed block instructions and the codebase, you come up with a proposal for this!"
    }},
    "test": {{
        "specification": "Given the entire codebase and the instructions, here we describe the test specification for the task at hand. We are aiming to just write ONE single test, which is able to infer whether the functionality update in the main code has been implemented correctly or not. Thus, the goal is is figure out if the task has been implemented correctly. Critically, the test needs to be fulfillable. We do NOT need to test anything else than the NEW functionality given the task specification. The rest of the code will be tested by other means anyways, so don't mention it. However, if you are forseeing that the new test will clash with an existing test, because maybe code will be replaced, then mention it in the field 'replacements'.",
        "data": "Describe in detail the input data for the test and the expected outcome. Use the provided codebase as a reference. The more detail the better, make it as concrete as possible.",
        "replacements": ["List of tests that need to be replaced by the new test. Use relative file paths as given in the codebase. Leave empty if no replacements are needed."]
    }},
    "write_files": ["List of files that may need to be written for the task. Use relative file paths as given in the codebase."],
    "context_files": ["List of files that need to be read for context in order to implement the task and as background information for the test. Use relative file paths as given in the codebase."],
    "commit_message": "Brief commit message about your changes."
}}
--------------------
Now here are the instructions to make this json file:
Please analyze the codebase and provide a protoblock that addresses this task: {task_instructions}"""
    
    def create_protoblock(self, seed_instructions: str) -> ProtoBlockSpec:
        """
        Create a protoblock from seed instructions that contain all necessary information.
        
        Args:
            seed_instructions: Complete instructions for the LLM to generate the protoblock
            
        Returns:
            ProtoBlockSpec object containing the protoblock specification
        """
        # Create messages for LLM
        messages = [
            Message(role="system", content="You are a helpful assistant that generates JSON protoblocks for code tasks. Follow the template exactly and ensure the output is valid JSON. Do not use markdown code fences in your response."),
            Message(role="user", content=seed_instructions)
        ]
        
        # Get response from LLM
        response = self.llm_client.chat_completion(messages)
        json_content = response.strip()
        
        # Strip markdown code fences if present
        if json_content.startswith("```"):
            lines = json_content.split("\n")
            start_idx = next((i for i, line in enumerate(lines) if line.startswith("```")), 0) + 1
            end_idx = next((i for i, line in enumerate(lines[start_idx:], start_idx) if line.startswith("```")), len(lines))
            json_content = "\n".join(lines[start_idx:end_idx]).strip()
        
        # Parse JSON content
        try:
            data = json.loads(json_content)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON response from LLM: {e}")
        
        # Create ProtoBlockSpec with short UUID (6 characters)
        return ProtoBlockSpec(
            task_specification=data["task"]["specification"],
            test_specification=data["test"]["specification"],
            test_data=data["test"]["data"],
            write_files=data["write_files"],
            context_files=data.get("context_files", []),
            commit_message=f"TDAC: {data.get('commit_message', 'Update')}",
            block_id=str(uuid.uuid4())[:6]
        )
    
    def save_protoblock(self, spec: ProtoBlockSpec, template_type: str) -> str:
        """
        Save a protoblock specification to a file.
        
        Args:
            spec: ProtoBlockSpec object containing the specification
            template_type: Type of template used
            
        Returns:
            Path to the saved protoblock file
        """
        data = {
            "task": {
                "specification": spec.task_specification
            },
            "test": {
                "specification": spec.test_specification,
                "data": spec.test_data,
                "replacements": spec.write_files
            },
            "write_files": spec.write_files,
            "context_files": spec.context_files,
            "commit_message": spec.commit_message
        }
        
        # Save to file using just the block_id
        filename = f".tdac_protoblock_{spec.block_id}.json"
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
            
        return filename 