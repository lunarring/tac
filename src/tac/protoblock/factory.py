import json
import uuid
from typing import List, Optional, Tuple
from datetime import datetime
import os
import logging
import time

from tac.utils.file_gatherer import gather_python_files
from tac.utils.project_files import ProjectFiles
from tac.core.llm import LLMClient, Message
from .protoblock import ProtoBlock

logger = logging.getLogger(__name__)

class ProtoBlockFactory:
    """Factory class for creating protoblocks"""
    
    def __init__(self):
        self.llm_client = LLMClient(strength="strong")
        self.project_files = ProjectFiles()
    
    def _load_config(self) -> dict:
        """Load configuration from config.yaml"""
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'config.yaml')
        with open(config_path, 'r') as f:
            import yaml
            return yaml.safe_load(f)

    def get_protoblock_genesis_prompt(self, codebase: str, task_instructions: str) -> str:
        """
        Args:
            codebase: The codebase content to analyze (result of gather_python_files)
            task_instructions: The specific task instructions to use
            
        Returns:
            str: Complete protoblock genesis prompt for the LLM
        """
        # Load config to check if summaries are enabled
        config = self._load_config()
        use_summaries = config.get('general', {}).get('use_file_summaries', False)
        
        # Get codebase content, using summaries if enabled
        if use_summaries:
            logger.info("Using file summaries for seed instructions")
            codebase = gather_python_files(
                directory=".",  # Always use project root
                exclusions=[".git", "__pycache__"],
                use_summaries=True
            )
        
        return f"""<purpose>
    You are a senior python software engineer. You are specialized in updating codebases and precisely formulating instructions for your your junior software engineer employee, who then implements the final code. You have access to the <codebase> and <task_instructions> from the boss. You follow strictly the <output_format> below, which is a JSON object. You also follow the <planning_rules> below.
</purpose>

<codebase>
{codebase}
</codebase>

<task_instructions>
{task_instructions}
</task_instructions>

<planning_rules>
- Create a plan how this task could be implemented.
- Be sure that your plan also integrates the new functionality into the existing codebase and makes sure that some parts are replaced if needed.
- Scan the codebase and review carefully and list every file that could potentially be needed for read or write access (read for context and write for making changes)
- Design a test that could be used to verify if the task has been implemented correctly, particularly if the integration is correct. The test should be as close as possible to the real usage of the code.
- Make a plan how to ensure that existing functionality is not broken by the changes.
- Bring everything into the right format and structure.
</planning_rules>

stick exactly to the following output_format, filling in between <>
<output_format>
{{
    "task": {{
        "specification": "<>",
    }},
    "test": {{
        "specification": "<>",
        "data": "<>"
    }},
    "write_files": [<>"],
    "context_files": ["<>"],
    "commit_message": "<>"
}}
</output_format_explained>

<output_format_explained>
{{
    "task": {{
        "specification": "Given the entire codebase and the task instructions below, we describe the task at hand very precisely and actionable, make a high level plan of what we want to implement and how this on a high level could be achieved. Refrain from implementing the solution here, i.e. we are not describing exactly HOW the code needs to be changed but keep it higher level and super descriptive."
    }},
    "test": {{
        "specification": "Given the entire codebase and the instructions, here we describe the test specification for the task above. We are aiming to just write ONE single test ideally, which is able to infer whether the functionality update in the code has been implemented correctly or not. Thus, the goal is is figure out if the task instructions have been implemented correctly. Critically, the test needs to be fulfillable. We just need a test for the new task! It should be a test that realistically can be executed, be careful for instance with tests that would spawn UI and then everything blocks!",
        "data": "Describe in detail the input data for the test and the expected outcome. Use the provided codebase as a reference. The more detail the better, make it as concrete as possible."
    }},
    "write_files": ["List of files that may need to be written for the task. Scan the codebase and review carefully and include every file that need to be changed for the task. Use relative file paths as given in the codebase. Be sure to include everything that could potentially be needed for write access! Test files should only be created in tests/test_*.py for instance tests/test_piano_trainer_main.py. ALWAYS include the test files here, never skip them!"],
    "context_files": ["List of files that need to be read for context in order to implement the task and as background information for the test. Scan the codebase and review carefully and include every file that need to be read for the task. Use relative file paths as given in the codebase. Be sure to provide enough context!"],
    "commit_message": "Brief commit message about your changes."
}}
</output_format_explained>"""

    def verify_protoblock(self, json_content: str) -> Tuple[bool, str, Optional[dict]]:
        """
        Verifies that a protoblock JSON is valid and contains all required fields.
        First tries to parse as-is, only cleans code fences if that fails.
        
        Args:
            json_content: The JSON content to validate
            
        Returns:
            Tuple[bool, str, Optional[dict]]: (is_valid, error_message, parsed_data)
        """
        if not json_content or not json_content.strip():
            return False, "Empty JSON content", None
            
        content_to_try = json_content.strip()
        data = None
        
        # Try parsing with different methods
        parse_methods = [
            lambda x: json.loads(x),  # Try direct parsing first
            lambda x: json.loads(self._llm_client.clean_code_fences(x))  # Try cleaning code fences if direct fails
        ]
        
        parse_error = None
        for parse_method in parse_methods:
            try:
                data = parse_method(content_to_try)
                break
            except json.JSONDecodeError as e:
                parse_error = str(e)
                continue
            except Exception as e:
                return False, f"Unexpected error parsing JSON: {str(e)}", None
                
        if data is None:
            return False, f"Failed to parse JSON: {parse_error}", None
            
        try:
            # Verify top-level structure
            if not isinstance(data, dict):
                return False, "JSON content must be a dictionary", None
                
            # Define required structure - only check these keys, ignore additional ones
            required_structure = {
                "task": {
                    "required_keys": ["specification"],
                    "type": dict
                },
                "test": {
                    "required_keys": ["specification", "data"],
                    "type": dict
                },
                "write_files": {
                    "type": list
                },
                "context_files": {
                    "type": list
                },
                "commit_message": {
                    "type": str
                }
            }
            
            # Extract only the required fields for validation, but keep optional fields
            validated_data = {}
            
            # First validate and extract required fields
            for key in required_structure:
                if key not in data:
                    return False, f"Missing required key: {key}", None
                validated_data[key] = data[key]
            
            # Add any optional fields that might be useful (like analysis)
            for key in data:
                if key not in required_structure:
                    validated_data[key] = data[key]
            
            # Validate structure
            for key, requirements in required_structure.items():
                # Check if required key exists
                if key not in validated_data:
                    return False, f"Missing required key: {key}", None
                    
                # Check type
                if not isinstance(validated_data[key], requirements["type"]):
                    return False, f"{key} must be a {requirements['type'].__name__}", None
                    
                # Check nested required keys if any
                if "required_keys" in requirements and isinstance(validated_data[key], dict):
                    missing_nested = [k for k in requirements["required_keys"] if k not in validated_data[key]]
                    if missing_nested:
                        return False, f"{key} section missing keys: {', '.join(missing_nested)}", None
            
            # Additional validation for lists
            for key in ["write_files", "context_files"]:
                if not all(isinstance(item, str) for item in validated_data[key]):
                    return False, f"All items in {key} must be strings", None
                if not all(item.strip() for item in validated_data[key]):
                    return False, f"Empty or whitespace-only items not allowed in {key}", None

            # Validate test file naming convention and location
            for file_path in validated_data["write_files"]:
                if "test_" in file_path:
                    # Test files must be in tests/ directory with correct pattern
                    if not file_path.startswith("tests/test_") or not file_path.endswith(".py"):
                        return False, f"Test files must be in tests/ directory and follow pattern 'test_*.py', found: {file_path}", None
                    # No subfolders allowed in tests/
                    if file_path.count("/") > 1:
                        return False, f"Test files must be directly in tests/ directory (no subfolders allowed), found: {file_path}", None

            return True, "", validated_data
            
        except Exception as e:
            return False, f"Validation error: {str(e)}", None

    def create_protoblock(self, protoblock_genesis_prompt: str) -> ProtoBlock:
        """
        Create a protoblock from genesis prompt that contain all necessary information.
        Will retry creation based on max_retries_protoblock_creation from config.
        
        Args:
            protoblock_genesis_prompt: Complete instructions for the LLM to generate the protoblock
            
        Returns:
            ProtoBlock object containing the protoblock specification
            
        Raises:
            ValueError: If unable to create a valid protoblock after all retries
        """
        # Load config to check if summaries are enabled and get max retries
        config = self._load_config()
        use_summaries = config.get('general', {}).get('use_file_summaries', False)
        max_retries = config.get('general', {}).get('max_retries_protoblock_creation', 4)
        
        if use_summaries:
            logger.info("Using file summaries for protoblock creation")
            # Update all summaries first to ensure they're current
            self.project_files.update_summaries()
        
        # Create messages for LLM
        messages = [
            Message(role="system", content="You are a coding assistant. Output must be valid JSON with keys: 'task', 'test', 'write_files', 'context_files', 'commit_message'.No markdown, no code fences. Keep it short and strictly formatted."),
            Message(role="user", content=protoblock_genesis_prompt)
        ]
        
        last_error = None
        for attempt in range(max_retries):
            try:
                logger.info(f"Attempting protoblock creation (attempt {attempt + 1}/{max_retries})")
                
                # Get response from LLM
                response = self.llm_client.chat_completion(messages)
                
                # Check for empty or whitespace-only response
                if not response or not response.strip():
                    raise ValueError("Received empty response from LLM")
                    
                # Clean code fences from response
                response = self.llm_client._clean_code_fences(response)
                    
                # Log the raw response for debugging
                logger.debug(f"Raw LLM Response for protoblock:\n{response}")
                
                # Verify and parse the response
                is_valid, error_msg, data = self.verify_protoblock(response)
                if not is_valid:
                    # Include part of the response in the error message for context
                    preview = response[:200] + "..." if len(response) > 200 else response
                    raise ValueError(f"Invalid protoblock: {error_msg}\nResponse preview: {preview}")
                
                # Create ProtoBlock directly
                try:
                    return ProtoBlock(
                        task_description=data["task"]["specification"],
                        test_specification=data["test"]["specification"],
                        test_data_generation=data["test"]["data"],
                        write_files=data["write_files"],
                        context_files=data.get("context_files", []),
                        block_id=str(uuid.uuid4())[:6],
                        commit_message=f"TAC: {data.get('commit_message', 'Update')}"
                    )
                except KeyError as e:
                    raise ValueError(f"Missing required field in protoblock: {str(e)}\nData: {json.dumps(data, indent=2)}")
                    
            except Exception as e:
                last_error = e
                logger.warning(f"Protoblock creation failed (attempt {attempt + 1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    # Add a small delay before retrying to avoid rate limits
                    time.sleep(1)
                    continue
                
        # If we get here, all retries failed
        raise ValueError(f"Failed to create protoblock after {max_retries} attempts. Last error: {str(last_error)}")

    def save_protoblock(self, block: ProtoBlock, filename: Optional[str] = None) -> str:
        """
        Save a protoblock to a file.
        
        Args:
            block: ProtoBlock object to save
            filename: Optional filename to save to. If not provided, will use default format .tac_protoblock_{block_id}.json
            
        Returns:
            Path to the saved protoblock file
        """
        version_data = {
            "task": {
                "specification": block.task_description
            },
            "test": {
                "specification": block.test_specification,
                "data": block.test_data_generation,
                "replacements": block.write_files,
                "results": block.test_results if block.test_results else None  # Ensure test results are included
            },
            "write_files": block.write_files,
            "context_files": block.context_files,
            "commit_message": block.commit_message,
            "timestamp": datetime.now().isoformat()
        }
        
        # Use provided filename or generate default one
        if filename is None:
            filename = f".tac_protoblock_{block.block_id}.json"
        
        # Load existing data if file exists, otherwise create new structure
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                file_data = json.load(f)
                if not isinstance(file_data, dict) or 'versions' not in file_data:
                    # Convert old format to new format
                    file_data = {
                        'block_id': block.block_id,
                        'versions': [file_data]  # Old data becomes first version
                    }
        else:
            file_data = {
                'block_id': block.block_id,
                'versions': []
            }
        
        # Add new version
        file_data['versions'].append(version_data)
            
        with open(filename, 'w') as f:
            json.dump(file_data, f, indent=2)
            
        return filename

