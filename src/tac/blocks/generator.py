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
        
        # Get all agent-specific sections for the output format explained
        trusty_agents_prompts = TrustyAgentRegistry.generate_agent_prompts()

        # Get trusty agents description without plausibility
        trusty_agents_description = TrustyAgentRegistry.get_trusty_agents_description()
        
        # Extract just the agent names for the prompt
        agent_names = list(trusty_agents_description.keys())
        
        return f"""<purpose>
You are a senior python software engineer. You are specialized in figuring out how to phrase precise instructions for your employees who are junior software engineers and implement the final code. You have access to the <task_instructions> and <codebase>. The important aspect of your work is that you want to make sure that the resulting code can be easily verified. For this we have a palette of trusty agents from which you choose, and they can run an empirical verification of the code. Each trusty agent is specialized in a different aspect that they can test and your coding instructions and thinking should to be phrased in a way that we can maximize this verification process, given the chosen trusty agents.
</purpose>

<task_instructions>
{task_instructions}
</task_instructions>

<codebase>
{codebase}
</codebase>

<planning_rules>
- Examine carefully the codebase and the task instructions, and then develop a plan how this task could be implemented, but stay on the GOAL level and do not describe the exact implementation details.
- Think how this GOAL could be verified by the trusty agents. 
- Here are the available trusty agents, to you need to decide how we evaluate the code changes. Choose from this list of trusty agents: [{', '.join(agent_names)}]
- Here a description of what each trusty agent is capable of {trusty_agents_description}
- Select the most appropriate trusty agents that is capable of verifying the task. Select only one agent!
- Furthermore, we will need to supply two kinds of files to the coding agent:
    - context files: files that need to be read for context in order to implement the task and as background information for the test. Scan the codebase and review carefully and include every file that need to be read for the task. Use relative file paths as given in the codebase. Be sure to provide enough context! Test files should only be created in tests/test_*.py e.g. tests/test_piano_trainer_main.py.
    - write files: files that need to be written for the task. Scan the codebase and review carefully and include every file that need to be changed for the task. Use relative file paths as given in the codebase. Be sure to include everything that could potentially be needed for write access! 
- If we have an error analysis from the last implementation attempt, you should include it in the task instructions, expand them and make them longer to include as much detail as possible.

- Your response will be in two parts:
  1. A reasoning section (<reasoning>) where you think step by step about the task
  2. A protoblock section (<protoblock>) with the formal JSON specification
</planning_rules>

Your response should follow this format:

<reasoning>
1. Programming Language Analysis:
   - Identify the programming language being used
   - Note any relevant frameworks or libraries

2. Task Understanding:
   - Rephrase the task in your own words based on the context
   - Identify key requirements and constraints

3. Verification Strategy:
   - Analyze which trusty agent would be best for verification
   - Explain why this agent is most suitable for this task
   - Describe how the code changes will be verified

4. File Selection Strategy:
   - Explain your approach to selecting context and write files
   - Justify why these files are necessary
</reasoning>

<protoblock>
{{
    "task": "...",
    "write_files": ["..."],
    "context_files": ["..."],
    "commit_message": "...",
    "branch_name": "...",
    "trusty_agents": ["..."],
    "trusty_agent_prompts": {{
        "agent_name1": "generate here the prompt for the trusty agent 1",
        "agent_name2": "generate here the prompt for the trusty agent 2",
    }}
}}
</protoblock>

Available trusty agents and their capabilities:
{trusty_agents_description}

Agent prompts formatting:
{trusty_agents_prompts}"""

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
        
        # Store the original content to extract reasoning later
        original_content = json_content
            
        # Extract the JSON content from between <protoblock> tags if present
        if "<protoblock>" in json_content and "</protoblock>" in json_content:
            start_idx = json_content.find("<protoblock>") + len("<protoblock>")
            end_idx = json_content.find("</protoblock>")
            if start_idx < end_idx:
                json_content = json_content[start_idx:end_idx].strip()
            
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
                    "type": (str, list)  # Can be either a string or a list
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
                    "type": list
                },
                "trusty_agent_prompts": {
                    "type": dict
                }
            }
            
            # Extract only the required fields for validation, but keep optional fields
            validated_data = {}
            
            # Extract reasoning if present in the original content
            if "<reasoning>" in original_content and "</reasoning>" in original_content:
                start_idx = original_content.find("<reasoning>") + len("<reasoning>")
                end_idx = original_content.find("</reasoning>")
                if start_idx < end_idx:
                    validated_data["reasoning"] = original_content[start_idx:end_idx].strip()
            
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
                if isinstance(requirements["type"], tuple):
                    # Multiple allowed types
                    if not any(isinstance(validated_data[key], t) for t in requirements["type"]):
                        allowed_types = ", ".join(t.__name__ for t in requirements["type"])
                        return False, f"{key} must be one of these types: {allowed_types}", None
                else:
                    # Single allowed type
                    if not isinstance(validated_data[key], requirements["type"]):
                        return False, f"{key} must be a {requirements['type'].__name__}", None
            
            # Handle task field which can be a string or a list
            if isinstance(validated_data["task"], list):
                # If it's a list, join it into a string
                validated_data["task"] = {"specification": "\n".join(validated_data["task"])}
            elif isinstance(validated_data["task"], str):
                # If it's a string, wrap it in a dict
                validated_data["task"] = {"specification": validated_data["task"]}
            
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

            # Validate trusty_agents
            if not all(isinstance(item, str) for item in validated_data["trusty_agents"]):
                return False, "All items in trusty_agents must be strings", None
            
                
            # Validate trusty_agent_prompts
            if not all(isinstance(key, str) and isinstance(value, str) for key, value in validated_data["trusty_agent_prompts"].items()):
                return False, "All keys and values in trusty_agent_prompts must be strings", None

            # Validate test file naming convention and location - only for files in tests/ directory
            for file_path in validated_data["write_files"]:
                if file_path.startswith("tests/"):
                    # Test files must follow pattern 'test_*.py'
                    if not file_path.startswith("tests/test_"):
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
            Message(role="system", content="You are a coding assistant. Use the specified format with <reasoning> and <protoblock> sections."),
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
                    
                # Clean code fences from response if needed
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
                
                # Log reasoning section if it exists
                if "reasoning" in data:
                    logger.info("\n🤔 Reasoning Analysis:")
                    reasoning_lines = data["reasoning"].strip().split('\n')
                    for line in reasoning_lines:
                        logger.info(f"   {line}")
                    logger.info("") # Add an empty line for better separation
                
                # Create ProtoBlock directly
                try:
                    # Ensure pytest and plausibility are always included in trusty_agents
                    trusty_agents = data.get("trusty_agents", [])
                    if "pytest" not in trusty_agents:
                        trusty_agents.append("pytest")
                    if "plausibility" not in trusty_agents:
                        trusty_agents.append("plausibility")
                    
                    # Get trusty_agent_prompts
                    trusty_agent_prompts = data.get("trusty_agent_prompts", {})
                    
                    # Ensure plausibility uses the default prompt regardless of what was provided
                    # This ensures consistency since plausibility is excluded from user selection
                    if "plausibility" in trusty_agents:
                        default_prompt = TrustyAgentRegistry.get_protoblock_prompt("plausibility")
                        if default_prompt:
                            trusty_agent_prompts["plausibility"] = default_prompt
                    
                    # Get task specification
                    task_spec = data["task"]["specification"] if isinstance(data["task"], dict) else data["task"]
                    if isinstance(task_spec, list):
                        task_spec = "\n".join(task_spec)
                    
                    protoblock = ProtoBlock(
                        task_description=task_spec,
                        write_files=write_files,
                        context_files=context_files,
                        block_id=str(uuid.uuid4())[:6],
                        commit_message=f"tac: {data.get('commit_message', 'Update')}",
                        branch_name=data.get("branch_name"),
                        trusty_agents=trusty_agents,
                        trusty_agent_prompts=trusty_agent_prompts
                    )
                    logger.info("\nProtoblock details:")
                    logger.info(f"🎯 Task: {protoblock.task_description}")
                    logger.info(f"📝 Files to Write: {', '.join(protoblock.write_files)}")
                    logger.info(f"📚 Context Files: {', '.join(protoblock.context_files)}")
                    logger.info(f"💬 Commit Message: {protoblock.commit_message}")
                    logger.info(f"🤖 Trusty Agents: {', '.join(protoblock.trusty_agents)}")
                    logger.info(f"🔍 Trusty Agent Prompts: {json.dumps(protoblock.trusty_agent_prompts, indent=2)}")
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