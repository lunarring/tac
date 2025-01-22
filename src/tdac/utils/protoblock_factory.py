import json
import uuid
from dataclasses import dataclass
from typing import List, Optional, Tuple
from tdac.utils.file_gatherer import gather_python_files
from tdac.core.llm import LLMClient, Message
import os
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

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
            "instructions": """Conduct a thorough review of the entire codebase, focusing on one critical area to refactor only the single most problematic issue. For instance, that could mean reorganizing duplicated logic into a shared module or function, clarifying the intent of obscure variable names to make the code more self-explanatory, splitting excessively long methods into smaller, focused pieces, enforcing a consistent formatting style across all files, or adding robust error handling to improve stability. It may also involve consolidating configuration settings to a single source of truth, cleaning out unused or legacy code that no longer serves any purpose, replacing "magic numbers" with clearly named constants, or adopting modern language features to simplify and streamline key operations. The core goal is to address the underlying structural problems in the code so that it becomes easier to read, maintain, and extend—without altering the code's fundamental functionality. Consolidate  into well-designed, reusable functions or modules. This change is paramount to improving the maintainability and scalability of the codebase. Ensure that each consolidated function is properly named and documented. This targeted effort will lay the groundwork for a cleaner, more efficient project while simplifying collaboration for future contributors. HOWEVER KEEP IN MIND: PICK ONLY ONE SINGLE THING TO IMPLEMENT AND KEEP IT AS SIMPLE AS POSSIBLE!"""
        },
        "error": {
            "instructions": """An error occurred while running the code. Analyze the error message, trace through the codebase, and determine the root cause of the issue. Focus on ONE specific error and propose a solution."""
        },
        "test": {
            "instructions": """We want to add comprehensive tests to verify the existing functionality. Do NOT modify any code EXCEPT for the test files. We want to have maximum coverage of the codebase. Therefore you think through which would be a good test to add! Focus solely on creating this one robust, maintainable tests that document and verify the current behavior."""
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
--------------------
{{
    "task": {{
        "specification": "Given the entire codebase and the instructions, here we describe the task at hand very precisely. However we are not implementing the task here and we are not describing exactly HOW the code needs to be changed. You can come up with a proposal of how this could be achieved, but we do NOT need to implement it. Given your understanding of the seed block instructions and the codebase, you come up with a proposal for this!"
    }},
    "test": {{
        "specification": "Given the entire codebase and the instructions, here we describe the test specification for the task at hand. We are aiming to just write ONE single test, which is able to infer whether the functionality update in the main code has been implemented correctly or not. Thus, the goal is is figure out if the task has been implemented correctly. Critically, the test needs to be fulfillable. We do NOT need to test anything else than the NEW functionality given the task specification. It should be a test that realistically can be executed, be careful for instance with tests that would spawn UI and then everything blocks! The rest of the code will be tested by other means anyways, so don't mention it. However, if you are forseeing that the new test will clash with an existing test, because maybe code will be replaced, then mention it in the field 'replacements'.",
        "data": "Describe in detail the input data for the test and the expected outcome. Use the provided codebase as a reference. The more detail the better, make it as concrete as possible.",
        "replacements": ["List of tests that need to be replaced by the new test. Use relative file paths as given in the codebase. Leave empty if no replacements are needed."]
    }},
    "write_files": ["List of files that may need to be written for the task. Use relative file paths as given in the codebase."],
    "context_files": ["List of files that need to be read for context in order to implement the task and as background information for the test. Use relative file paths as given in the codebase."],
    "commit_message": "Brief commit message about your changes."
}}
--------------------
YOU NEED TO ADHERE TO THE JSON FORMAT ABOVE EXACTLY, as given in the example above between the fences.
Now here are the instructions to make this json file:
Please analyze the codebase and provide a protoblock that addresses this task.  : {task_instructions}"""
    
    def _clean_code_fences(self, content: str) -> str:
        """
        Clean markdown code fences from content, handling various formats.
        
        Args:
            content: The content to clean
            
        Returns:
            str: Content with code fences removed
        """
        # First strip whitespace
        cleaned = content.strip()
        
        # Handle various code fence patterns
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            
            # Skip first line regardless of what it contains (```json, ```, etc)
            start_idx = 1
            
            # Find end (last ``` or end of content)
            end_idx = len(lines)
            for i in range(len(lines) - 1, 0, -1):
                if lines[i].strip() == "```":
                    end_idx = i
                    break
            
            # Extract content between fences
            cleaned = "\n".join(lines[start_idx:end_idx]).strip()
            
            # If we still have content and it looks like JSON, return it
            if cleaned and cleaned.startswith("{"):
                return cleaned
            
            # If we don't have valid-looking JSON, try one more time with the original
            # This handles cases where the content might be wrapped multiple times
            return self._clean_code_fences(cleaned)
        
        return cleaned

    def verify_protoblock(self, json_content: str) -> Tuple[bool, str, Optional[dict]]:
        """
        Verifies that a protoblock JSON is valid and contains all required fields.
        First tries to parse as-is, only cleans code fences if that fails.
        
        Args:
            json_content: The JSON content to validate
            
        Returns:
            Tuple[bool, str, Optional[dict]]: (is_valid, error_message, parsed_data)
        """
        content_to_try = json_content.strip()
        
        # First try parsing as-is
        try:
            data = json.loads(content_to_try)
        except json.JSONDecodeError:
            # If that fails, try cleaning code fences
            try:
                cleaned_content = self._clean_code_fences(content_to_try)
                if not cleaned_content:
                    return False, "Content is empty after cleaning", None
                data = json.loads(cleaned_content)
            except json.JSONDecodeError as e:
                return False, f"Invalid JSON syntax: {str(e)}", None
        except Exception as e:
            return False, f"Validation error: {str(e)}", None
            
        try:
            # Verify top-level structure
            if not isinstance(data, dict):
                return False, "JSON content must be a dictionary", None
                
            required_keys = ["task", "test", "write_files", "context_files", "commit_message"]
            missing_keys = [key for key in required_keys if key not in data]
            if missing_keys:
                return False, f"Missing required keys: {', '.join(missing_keys)}", None
            
            # Verify task section
            if not isinstance(data["task"], dict):
                return False, "task must be a dictionary", None
            if "specification" not in data["task"]:
                return False, "task must contain 'specification'", None
                
            # Verify test section
            test = data["test"]
            if not isinstance(test, dict):
                return False, "test must be a dictionary", None
            test_keys = ["specification", "data", "replacements"]
            missing_test_keys = [key for key in test_keys if key not in test]
            if missing_test_keys:
                return False, f"test section missing keys: {', '.join(missing_test_keys)}", None
            if not isinstance(test["replacements"], list):
                return False, "test.replacements must be a list", None
                
            # Verify lists
            if not isinstance(data["write_files"], list):
                return False, "write_files must be a list", None
            if not isinstance(data["context_files"], list):
                return False, "context_files must be a list", None
                
            return True, "", data
            
        except Exception as e:
            return False, f"Validation error: {str(e)}", None

    def create_protoblock(self, seed_instructions: str) -> ProtoBlockSpec:
        """
        Create a protoblock from seed instructions that contain all necessary information.
        
        Args:
            seed_instructions: Complete instructions for the LLM to generate the protoblock
            
        Returns:
            ProtoBlockSpec object containing the protoblock specification
            
        Raises:
            ValueError: If unable to create a valid protoblock
        """
        # Create messages for LLM
        messages = [
            Message(role="system", content="You are a helpful assistant that generates JSON protoblocks for code tasks. Follow the template exactly and ensure the output is valid JSON. Do not use markdown code fences in your response."),
            Message(role="user", content=seed_instructions)
        ]
        
        # Get response from LLM
        response = self.llm_client.chat_completion(messages)
        
        # Check for empty or whitespace-only response
        if not response or not response.strip():
            raise ValueError("Received empty response from LLM")
            
        # Log the raw response for debugging
        logger.debug(f"Raw LLM Response for protoblock:\n{response}")
        
        # Verify and parse the response
        is_valid, error_msg, data = self.verify_protoblock(response)
        if not is_valid:
            # Include part of the response in the error message for context
            preview = response[:200] + "..." if len(response) > 200 else response
            raise ValueError(f"Invalid protoblock: {error_msg}\nResponse preview: {preview}")
        
        # Create ProtoBlockSpec with short UUID (6 characters)
        try:
            return ProtoBlockSpec(
                task_specification=data["task"]["specification"],
                test_specification=data["test"]["specification"],
                test_data=data["test"]["data"],
                write_files=data["write_files"],
                context_files=data.get("context_files", []),
                commit_message=f"TDAC: {data.get('commit_message', 'Update')}",
                block_id=str(uuid.uuid4())[:6]
            )
        except KeyError as e:
            raise ValueError(f"Missing required field in protoblock: {str(e)}\nData: {json.dumps(data, indent=2)}")
    
    def save_protoblock(self, spec: ProtoBlockSpec, template_type: str) -> str:
        """
        Save a protoblock specification to a file.
        
        Args:
            spec: ProtoBlockSpec object containing the specification
            template_type: Type of template used
            
        Returns:
            Path to the saved protoblock file
        """
        version_data = {
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
            "commit_message": spec.commit_message,
            "timestamp": datetime.now().isoformat()
        }
        
        # Save to file using just the block_id
        filename = f".tdac_protoblock_{spec.block_id}.json"
        
        # Load existing data if file exists, otherwise create new structure
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                file_data = json.load(f)
                if not isinstance(file_data, dict) or 'versions' not in file_data:
                    # Convert old format to new format
                    file_data = {
                        'block_id': spec.block_id,
                        'template_type': template_type,
                        'versions': [file_data]  # Old data becomes first version
                    }
        else:
            file_data = {
                'block_id': spec.block_id,
                'template_type': template_type,
                'versions': []
            }
        
        # Add new version
        file_data['versions'].append(version_data)
            
        with open(filename, 'w') as f:
            json.dump(file_data, f, indent=2)
            
        return filename 