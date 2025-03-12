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
from tac.core.config import config
from .model import ProtoBlock
from tac.trusty_agents.registry import TrustyAgentRegistry

logger = logging.getLogger(__name__)

class ProtoBlockGenerator:
    """
    Creates structured task specifications (ProtoBlocks) from high-level instructions.
    
    Workflow:
    1. Analyzes codebase and task instructions
    2. Generates a comprehensive task specification in JSON format
    3. Validates the specification structure
    4. Creates a ProtoBlock object ready for execution
    
    Uses LLM to transform abstract requirements into concrete implementation plans.
    """
    
    def __init__(self):
        self.llm_client = LLMClient(llm_type="strong")
        self.project_files = ProjectFiles()
    
    def get_protoblock_genesis_prompt(self, codebase: str, task_instructions: str) -> str:
        """
        Args:
            codebase: The codebase content to analyze (result of gather_python_files)
            task_instructions: The specific task instructions to use
            
        Returns:
            str: Complete protoblock genesis prompt for the LLM
        """
        codebase = self.project_files.get_codebase_summary()
        
        # Get the trusty agents prompt section
        trusty_agents_section = TrustyAgentRegistry.generate_trusty_agents_prompt_section()
        
        # Get all agent-specific sections for the output format
        agent_sections_output = TrustyAgentRegistry.generate_agent_sections_for_output_format()
        
        # Get all agent-specific sections for the output format explained
        trusty_agents_prompts = TrustyAgentRegistry.generate_agent_prompts()

        trusty_agents_description = TrustyAgentRegistry.get_trusty_agents_description()

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
- Examine carefully the codebase and the task instructions, and then develop a plan how this task could be implemented, but stay on the GOAL level and do not describe the exact implementation details.
- We will need to supply two kinds of files to the coding agent:
    - context files: files that need to be read for context in order to implement the task and as background information for the test. Scan the codebase and review carefully and include every file that need to be read for the task. Use relative file paths as given in the codebase. Be sure to provide enough context! Test files should only be created in tests/test_*.py e.g. tests/test_piano_trainer_main.py.
    - write files: files that need to be written for the task. Scan the codebase and review carefully and include every file that need to be changed for the task. Use relative file paths as given in the codebase. Be sure to include everything that could potentially be needed for write access! 
- Here are the available trusty agents, to you need to decide how we evaluate the code changes. Choose from this list of trusty agents: [{', '.join(trusty_agents_description.keys())}]
- Here a description of what each trusty agent is capable of {trusty_agents_description}
- Select the most appropriate trusty agents for the task, it is good if there are multiple.
- The output format is two JSONs, you need to follow the format as described below. The first JSON is for the coding agents, and the second JSON is for the trusty agents that give trust assurances for the code changes.
</planning_rules>

stick exactly to the following output_format, filling in between ...
<output_format>
{{
    "task": ["..."],
    "write_files": ["..."],
    "context_files": ["..."],
    "commit_message": "...",
    "branch_name": "...",
}}
{{
    "trusty_agents": ["..."],
    "trusty_agent_configs": {{
        "agent_name": {{
            "config": "..."
        }}
    }}
}}
</output_format>

And here a bit more detailed explanation of the output format:

<output_format_explained>
{{
    "task": "Given the entire codebase and the task instructions below, we describe the task at hand very precisely and actionable, however mainly in terms og goals that we want to achieve. Thus make a high level plan of what we want to implement and how this on a high level could be achieved. Refrain from implementing the solution here, i.e. we are not describing exactly HOW the code needs to be changed but keep it higher level and super descriptive.",
    "write_files": ["List of files that may need to be written for the task. Scan the codebase and review carefully and include every file that need to be changed for the task. Use relative file paths as given in the codebase. Be sure to include everything that could potentially be needed for write access! Test files should only be created in tests/test_*.py for instance tests/test_piano_trainer_main.py. ALWAYS include the test files here, never skip them! If there is a similar test in our codebase, we definitely want to write into the same test file and append the new test."],
    "context_files": ["List of files that need to be read for context in order to implement the task and as background information for the test. Scan the codebase and review carefully and include every file that need to be read for the task. Use relative file paths as given in the codebase. Be sure to provide enough context!"],
    "commit_message": "Brief commit message about your changes.",
    "branch_name": "Name of the branch to create for this task. Use the task description as a basis for the branch name, the branch name always starts with tac/ e.g.  tac/feature/new-user-authentication or tac/bugfix/fix_login_issue.",
}}

{{
    "trusty_agents": ["List of trusty agents to use for this task. Choose from the following list: {', '.join(trusty_agents_description.keys())}]",
    "trusty_agent_prompts": {{
        "agent_name1": "... fill in here the prompt for the trusty agent 1",
        "agent_name2": "... fill in here the prompt for the trusty agent 2",
    }}
}}

To fill in the trusty_agent_prompts, it really depends on your choice of trusty agents. When you know which trusty agents you are using, you can use the following guidelines to obtain the prompt for the trusty agents.
{trusty_agents_prompts}
</output_format_explained>"""

    def verify_protoblock(self, json_content: str) -> Tuple[bool, str, Optional[dict]]:
        """
        Verifies that a protoblock JSON is valid and contains all required fields.
        First tries to parse as-is, only cleans code fences if that fails.
        Pytest sections can be empty strings if no test is needed.
        
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
            lambda x: json.loads(self.llm_client._clean_code_fences(x))  # Try cleaning code fences if direct fails
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
                "pytest": {
                    "required_keys": ["specification"],
                    "type": dict,
                    "allow_empty": True  # New flag to indicate empty values are allowed
                },
                "write_files": {
                    "type": list
                },
                "context_files": {
                    "type": list
                },
                "commit_message": {
                    "type": str
                },
                "branch_name": {
                    "type": str
                },
                "trusty_agents": {
                    "type": list,
                    "optional": True  # This field is optional
                }
            }
            
            # Extract only the required fields for validation, but keep optional fields
            validated_data = {}
            
            # First validate and extract required fields
            for key in required_structure:
                # Skip optional fields if they don't exist in the data
                if required_structure[key].get("optional", False) and key not in data:
                    continue
                if key not in data:
                    return False, f"Missing required key: {key}", None
                validated_data[key] = data[key]
            
            # Add any optional fields that might be useful (like analysis)
            for key in data:
                if key not in required_structure:
                    validated_data[key] = data[key]
            
            # Validate structure
            for key, requirements in required_structure.items():
                # Skip optional fields if they don't exist in validated_data
                if requirements.get("optional", False) and key not in validated_data:
                    continue
                # Check if required key exists
                if key not in validated_data:
                    return False, f"Missing required key: {key}", None
                    
                # Check type
                if not isinstance(validated_data[key], requirements["type"]):
                    return False, f"{key} must be a {requirements['type'].__name__}", None
                    
                # Check nested required keys if any
                if "required_keys" in requirements and isinstance(validated_data[key], dict):
                    # For pytest section, allow empty strings for required fields
                    allow_empty = requirements.get("allow_empty", False)
                    if allow_empty and key == "pytest":
                        # Ensure all required keys exist but can be empty strings
                        for req_key in requirements["required_keys"]:
                            if req_key not in validated_data[key]:
                                return False, f"{key} section missing key: {req_key}", None
                            # Allow empty string for pytest section fields
                            if not isinstance(validated_data[key][req_key], str):
                                validated_data[key][req_key] = ""
                    else:
                        missing_nested = [k for k in requirements["required_keys"] if k not in validated_data[key]]
                        if missing_nested:
                            return False, f"{key} section missing keys: {', '.join(missing_nested)}", None
            
            # Additional validation for lists
            for key in ["write_files", "context_files"]:
                if not all(isinstance(item, str) for item in validated_data[key]):
                    return False, f"All items in {key} must be strings", None
                if not all(item.strip() for item in validated_data[key]):
                    return False, f"Empty or whitespace-only items not allowed in {key}", None

                # Ensure all paths are relative (not absolute)
                for i, item in enumerate(validated_data[key]):
                    if os.path.isabs(item):
                        # Convert absolute path to relative path
                        try:
                            rel_path = os.path.relpath(item)
                            validated_data[key][i] = rel_path
                            logger.warning(f"Converted absolute path '{item}' to relative path '{rel_path}' in {key}")
                        except ValueError:
                            return False, f"Cannot convert absolute path '{item}' to relative path in {key}", None

            # Validate trusty_agents if present
            if "trusty_agents" in validated_data:
                if not all(isinstance(item, str) for item in validated_data["trusty_agents"]):
                    return False, "All items in trusty_agents must be strings", None
                
                # Ensure pytest and plausibility are always included
                if "pytest" not in validated_data["trusty_agents"]:
                    validated_data["trusty_agents"].append("pytest")
                if "plausibility" not in validated_data["trusty_agents"]:
                    validated_data["trusty_agents"].append("plausibility")
            else:
                # Set default value if not present
                validated_data["trusty_agents"] = config.general.default_trusty_agents
                # Ensure pytest and plausibility are always included
                if "pytest" not in validated_data["trusty_agents"]:
                    validated_data["trusty_agents"].append("pytest")
                if "plausibility" not in validated_data["trusty_agents"]:
                    validated_data["trusty_agents"].append("plausibility")

            # Validate test file naming convention and location - only for files in tests/ directory
            for file_path in validated_data["write_files"]:
                if file_path.startswith("tests/"):
                    # Test files must follow pattern 'test_*.py'
                    if not file_path.startswith("tests/test_") or not file_path.endswith(".py"):
                        return False, f"Files in tests/ directory must follow pattern 'test_*.py', found: {file_path}", None
                    # No subfolders allowed in tests/
                    if file_path.count("/") > 1:
                        return False, f"Files in tests/ directory must be directly in tests/ (no subfolders allowed), found: {file_path}", None

            return True, "", validated_data
            
        except Exception as e:
            return False, f"Validation error: {str(e)}", None

    def create_protoblock(self, protoblock_genesis_prompt: str, protoblock: Optional[ProtoBlock] = None) -> ProtoBlock:
        """
        Create a protoblock from genesis prompt that contain all necessary information.
        Will retry creation based on max_retries_protoblock_creation from config.
        
        Args:
            protoblock_genesis_prompt: Complete instructions for the LLM to generate the protoblock
            protoblock: Optional existing ProtoBlock object. If provided, it will be returned directly
                        without creating a new one.
            
        Returns:
            ProtoBlock object containing the protoblock specification
            
        Raises:
            ValueError: If unable to create a valid protoblock after all retries
        """
        # If protoblock is provided, return it directly
        if protoblock is not None:
            logger.info("Using provided protoblock, skipping creation process")
            return protoblock
            
        # Use centralized config
        use_summaries = config.general.use_file_summaries
        max_retries = config.general.max_retries_protoblock_creation
        
        if use_summaries:
            logger.info("Using file summaries for protoblock creation")
            # Update all summaries first to ensure they're current
            self.project_files.update_summaries()
        
        # Create messages for LLM
        messages = [
            Message(role="system", content="You are a coding assistant. Output must be valid JSON with keys: 'task', 'pytest', 'write_files', 'context_files', 'commit_message'. The 'pytest' key should only have a 'specification' field. No markdown, no code fences. Keep it short and strictly formatted."),
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
                    
                # Verify and parse the response
                is_valid, error_msg, data = self.verify_protoblock(response)
                if not is_valid:
                    # Include part of the response in the error message for context
                    preview = response[:200] + "..." if len(response) > 200 else response
                    raise ValueError(f"Invalid protoblock: {error_msg}\nResponse preview: {preview}")
                
                # Ensure all paths are relative
                write_files = [os.path.relpath(path) if os.path.isabs(path) else path for path in data["write_files"]]
                context_files = [os.path.relpath(path) if os.path.isabs(path) else path for path in data.get("context_files", [])]

                # Remove any context files that are also in write_files to avoid duplication
                context_files = [file for file in context_files if file not in write_files]
                
                # Create ProtoBlock directly
                try:
                    # Ensure pytest and plausibility are always included in trusty_agents
                    trusty_agents = data.get("trusty_agents", config.general.default_trusty_agents)
                    if "pytest" not in trusty_agents:
                        trusty_agents.append("pytest")
                    if "plausibility" not in trusty_agents:
                        trusty_agents.append("plausibility")
                    
                    protoblock = ProtoBlock(
                        task_description=data["task"]["specification"],
                        pytest_specification=data["pytest"]["specification"],
                        pytest_data_generation=data["pytest"]["specification"],
                        write_files=write_files,
                        context_files=context_files,
                        block_id=str(uuid.uuid4())[:6],
                        commit_message=f"tac: {data.get('commit_message', 'Update')}",
                        branch_name=data.get("branch_name"),
                        trusty_agents=trusty_agents
                    )
                    logger.info("\nProtoblock details:")
                    logger.info(f"🎯 Task: {protoblock.task_description}")
                    logger.info(f"🧪 Pytest Specification: {protoblock.pytest_specification}")
                    logger.info(f"📊 Pytest Data Generation: {protoblock.pytest_data_generation}")
                    logger.info(f"📝 Files to Write: {', '.join(protoblock.write_files)}")
                    logger.info(f"📚 Context Files: {', '.join(protoblock.context_files)}")
                    logger.info(f"💬 Commit Message: {protoblock.commit_message}")
                    logger.info(f"🤖 Trusty Agents: {', '.join(protoblock.trusty_agents)}\n")
                    logger.info("🚀 Starting protoblock execution...\n")
                    return protoblock
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