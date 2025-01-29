import json
import uuid
from typing import List, Optional, Tuple
from datetime import datetime
import os
import logging

from tac.utils.file_gatherer import gather_python_files
from tac.utils.project_files import ProjectFiles
from tac.core.llm import LLMClient, Message
from .protoblock import ProtoBlock

logger = logging.getLogger(__name__)

class ProtoBlockFactory:
    """Factory class for creating protoblocks"""
    
    # Predefined templates for different task types
    TEMPLATES = {
        "refactor": {
            "instructions": (
                "Review the codebase and address one problematic area (e.g., duplicated logic, unclear naming, large functions). Improve it without changing fundamental logic. Keep the change small and focused."
            )
        },
        "error": {
            "instructions": (
                "Analyze the following error, identify its root cause, and propose a fix. Include ALL files that are mentioned in the error message in the write_files field."
            )
        },
        "test": {
            "instructions": (
                "Add one well-targeted test that validates newly implemented or existing functionality. Focus on clarity and maintainability of this single test. New test files should only be created in test/test_*.py."
            )
        }
    }
    
    def __init__(self):
        self.llm_client = LLMClient(strength="strong")
        self.project_files = ProjectFiles()
    
    def _load_config(self) -> dict:
        """Load configuration from config.yaml"""
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'config.yaml')
        with open(config_path, 'r') as f:
            import yaml
            return yaml.safe_load(f)

    def _get_file_content(self, file_path: str, use_summaries: bool = False) -> str:
        """
        Get file content, either as full content or summary if enabled.
        
        Args:
            file_path: Path to the file
            use_summaries: Whether to use summaries instead of full content
            
        Returns:
            str: File content or summary
        """
        if not use_summaries:
            with open(file_path, 'r') as f:
                return f.read()
                
        # Try to get summary from cache
        summary = self.project_files.get_file_summary(file_path)
        if summary:
            if "error" in summary:
                logger.warning(f"Error in cached summary for {file_path}: {summary['error']}")
                return f"Error analyzing file: {summary['error']}"
            return f"File Summary:\n{summary['summary']}"
            
        # Generate new summary if not cached
        logger.info(f"Generating new summary for {file_path}")
        stats = self.project_files.update_summaries(exclusions=[".git", "__pycache__"])
        logger.debug(f"Summary update stats: {stats}")
        
        # Try to get summary again
        summary = self.project_files.get_file_summary(file_path)
        if summary:
            if "error" in summary:
                return f"Error analyzing file: {summary['error']}"
            return f"File Summary:\n{summary['summary']}"
            
        return f"Error: Could not generate summary for {file_path}"

    def get_task_instructions(self, template_type: Optional[str] = None, direct_instructions: Optional[str] = None) -> str:
        """
        Get task-specific instructions either from a template or direct instructions.
        If template_type is provided with direct_instructions, they will be combined.
        
        Args:
            template_type: Type of template to use (refactor, test, error)
            direct_instructions: Direct instructions provided by the user
            
        Returns:
            str: The task-specific instructions to use
            
        Raises:
            ValueError: If neither argument is provided, or if template type is invalid
        """
        if template_type is None and direct_instructions is None:
            raise ValueError("Must provide either template_type or direct_instructions")
            
        if template_type is not None and template_type not in self.TEMPLATES:
            raise ValueError(f"Invalid template type: {template_type}. Must be one of: {', '.join(self.TEMPLATES.keys())}")
            
        if template_type is None:
            return direct_instructions
            
        template_instructions = self.TEMPLATES[template_type]["instructions"]
        
        if not direct_instructions:
            return template_instructions
            
        # Special handling for error template
        if template_type == "error":
            return f"{template_instructions}\n\nError message:\n{direct_instructions}"
            
        # For other templates, combine with additional instructions
        return f"{template_instructions}\n\nAdditional specific instructions: {direct_instructions}"

    def get_seed_instructions(self, codebase: str, task_instructions: str) -> str:
        """
        Args:
            codebase: The codebase content to analyze (result of gather_python_files)
            task_instructions: The specific task instructions to use
            
        Returns:
            str: Complete seed instructions for the LLM
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
    You are a senior python software engineer. You are specialized in updating codebases and precisely formulating instructions for your employees, who then implement the solution.   complete seed instructions by combining codebase analysis with task instructions. Your own inputs are <codebase> and <task_instructions>. You follow strictly the <output_format> below, which is a JSON object. You also follow the <planning_rules> below.
</purpose>

<codebase>
{codebase}
</codebase>

<task_instructions>
{task_instructions}
</task_instructions>

<planning_rules>
- Create a plan how this task could be implemented.
- Scan the codebase and review carefully and list every file that could potentially be needed for read or write access.
- Design a test that could be used to verify if the task has been implemented correctly.
- Bring everything into the right format and structure.
</planning_rules>

<output_format>
{{
    "task": {{
        "specification": "Given the entire codebase and the task instructions below,  we describe the task at hand very precisely and actionable, making it easy and clear to implement. Refrain from implementing the solution here, i.e. we are not describing exactly HOW the code needs to be changed but keep it higher level and super descriptive. If helpful, you can come up with a proposal of how this could be achieved."
    }},
    "test": {{
        "specification": "Given the entire codebase and the instructions, here we describe the test specification for the task above. We are aiming to just write ONE single test ideally, which is able to infer whether the functionality update in the code has been implemented correctly or not. Thus, the goal is is figure out if the task instructions have been implemented correctly. Critically, the test needs to be fulfillable. We do NOT need to test anything else than the NEW functionality given the task specification. It should be a test that realistically can be executed, be careful for instance with tests that would spawn UI and then everything blocks!",
        "data": "Describe in detail the input data for the test and the expected outcome. Use the provided codebase as a reference. The more detail the better, make it as concrete as possible."
    }},
    "write_files": ["List of files that may need to be written for the task. Scan the codebase and review carefully and include every file that need to be changed for the task. Use relative file paths as given in the codebase. Be sure to include everything that could potentially be needed for write access! Test files should only be created in test/test_*.py for instance tests/test_piano_trainer_main.py"],
    "context_files": ["List of files that need to be read for context in order to implement the task and as background information for the test. Scan the codebase and review carefully and include every file that need to be read for the task. Use relative file paths as given in the codebase. Be sure to provide enough context!"],
    "commit_message": "Brief commit message about your changes."
}}
</output_format>"""

    def _clean_code_fences(self, content: str) -> str:
        """
        Clean markdown code fences and comments from content.
        Handles JSON content more intelligently.
        
        Args:
            content: The content to clean
            
        Returns:
            str: Cleaned content ready for JSON parsing
        """
        if not content or not content.strip():
            return ""
            
        # First clean any markdown code fences
        lines = content.strip().split('\n')
        if content.strip().startswith("```"):
            # Find the content between the code fences
            start_idx = 1  # Skip the opening fence
            end_idx = len(lines)
            
            for i in range(len(lines) - 1, 0, -1):
                if lines[i].strip() == "```":
                    end_idx = i
                    break
                    
            lines = lines[start_idx:end_idx]
        
        # Now clean the lines
        cleaned_lines = []
        in_string = False
        string_char = None
        
        for line in lines:
            cleaned_line = []
            i = 0
            while i < len(line):
                char = line[i]
                
                # Handle string literals
                if char in ['"', "'"] and (i == 0 or line[i-1] != '\\'):
                    if not in_string:
                        in_string = True
                        string_char = char
                    elif char == string_char:
                        in_string = False
                        string_char = None
                
                # Handle comments only if we're not in a string
                elif char == '/' and i + 1 < len(line) and line[i + 1] == '/' and not in_string:
                    break
                
                cleaned_line.append(char)
                i += 1
            
            # Only add non-empty lines
            cleaned = ''.join(cleaned_line).strip()
            if cleaned:
                cleaned_lines.append(cleaned)
        
        return '\n'.join(cleaned_lines)

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
            lambda x: json.loads(self._clean_code_fences(x))  # Try cleaning code fences if direct fails
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

            # Validate test file naming convention
            for file_path in validated_data["write_files"]:
                if file_path.startswith("tests/"):
                    # Ensure test files are directly in tests/ directory and follow naming convention
                    parts = file_path.split("/")
                    if len(parts) > 2:
                        return False, f"Test files must be directly in tests/ directory, found: {file_path}", None
                    if not parts[1].startswith("test_") or not parts[1].endswith(".py"):
                        return False, f"Test files must follow pattern 'test_*.py', found: {file_path}", None
            
            return True, "", validated_data
            
        except Exception as e:
            return False, f"Validation error: {str(e)}", None

    def create_protoblock(self, seed_instructions: str) -> ProtoBlock:
        """
        Create a protoblock from seed instructions that contain all necessary information.
        
        Args:
            seed_instructions: Complete instructions for the LLM to generate the protoblock
            
        Returns:
            ProtoBlock object containing the protoblock specification
            
        Raises:
            ValueError: If unable to create a valid protoblock
        """
        # Load config to check if summaries are enabled
        config = self._load_config()
        use_summaries = config.get('general', {}).get('use_file_summaries', False)
        
        if use_summaries:
            logger.info("Using file summaries for protoblock creation")
            # Update all summaries first to ensure they're current
            self.project_files.update_summaries()
        
        # Create messages for LLM
        messages = [
            Message(role="system", content="You are a coding assistant. Output must be valid JSON with keys: 'task', 'test', 'write_files', 'context_files', 'commit_message'.No markdown, no code fences. Keep it short and strictly formatted."),
            Message(role="user", content=seed_instructions)
        ]
        
        # Get response from LLM
        response = self.llm_client.chat_completion(messages)
        
        # Check for empty or whitespace-only response
        if not response or not response.strip():
            raise ValueError("Received empty response from LLM")
            
        # Clean code fences from response
        response = self._clean_code_fences(response)
            
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

    def save_protoblock(self, block: ProtoBlock) -> str:
        """
        Save a protoblock to a file.
        
        Args:
            block: ProtoBlock object to save
            
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
        
        # Save to file using just the block_id
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

    def create_next_protoblock_with_test_results(self, previous_block: ProtoBlock, test_results: str) -> ProtoBlock:
        """
        Creates a new protoblock for the next attempt by analyzing test results and improving the approach.
        
        Args:
            previous_block: Previous ProtoBlock instance that failed
            test_results: Test results from the previous attempt
            
        Returns:
            ProtoBlock: A new protoblock instance with improved instructions and context
        """
        analysis_prompt = f"""<purpose>
You are a senior python software engineer analyzing a failed implementation attempt. Your goal is to understand what went wrong and create an improved plan for the next attempt.
</purpose>

<previous_json>
Task Description: {previous_block.task_description}
Test Specification: {previous_block.test_specification}
Test Data: {previous_block.test_data_generation}
Files to Write: {previous_block.write_files}
Context Files: {previous_block.context_files}
</previous_json>

<test_results>
{test_results}
</test_results>

<planning_rules>
- Analyze the <test_results> to identify what exactly went wrong and how to overcome the errors that were raised
- Consider if we're missing any necessary files in write_files or context_files
- Check if the <previous_json> needs more clarity or specificity
- Evaluate if the test specification or data need adjustments
</planning_rules>

<output_format>
{{
    "task": {{
        "specification": "Improved task description with clearer instructions"
    }},
    "test": {{
        "specification": "Refined test specification based on previous failure",
        "data": "Updated test data if needed"
    }},
    "write_files": ["Updated list of files that need to be modified"],
    "context_files": ["Updated list of files needed for context"],
    "commit_message": "Brief description of the revised approach"
}}
</output_format>"""

        # Get analysis and improvements from LLM
        messages = [
            Message(role="system", content="You are a coding assistant analyzing test failures and improving implementation plans. Output must be valid JSON."),
            Message(role="user", content=analysis_prompt)
        ]
        
        response = self.llm_client.chat_completion(messages)
        logger.debug(f"Raw LLM response (updated): {response}")
        # Clean code fences from response
        response = self._clean_code_fences(response)
        
        # Verify and parse the response
        is_valid, error_msg, data = self.verify_protoblock(response)
        if not is_valid:
            logger.warning(f"Failed to get valid improvement suggestions: {error_msg}")
            # Fallback to original behavior if LLM analysis fails
            return ProtoBlock(
                task_description=previous_block.task_description,
                test_specification=previous_block.test_specification,
                test_data_generation=previous_block.test_data_generation,
                write_files=previous_block.write_files,
                context_files=previous_block.context_files,
                block_id=previous_block.block_id,
                commit_message=previous_block.commit_message,
                test_results=test_results
            )
            
        # Create new protoblock with improvements
        next_block = ProtoBlock(
            task_description=data["task"]["specification"],
            test_specification=data["test"]["specification"],
            test_data_generation=data["test"]["data"],
            write_files=data["write_files"],
            context_files=data["context_files"],
            block_id=previous_block.block_id,
            commit_message=previous_block.commit_message,
            test_results=test_results
        )
        
        # Save the updated protoblock
        self.save_protoblock(next_block)
        
        return next_block 