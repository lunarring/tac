from typing import Dict, Optional, Tuple
import logging
import json
from datetime import datetime
from tdac.core.llm import LLMClient, Message
from tdac.utils.file_gatherer import gather_python_files
from tdac.utils.protoblock_factory import ProtoBlockSpec

logger = logging.getLogger(__name__)

class ProtoBlockReflector:
    """Analyzes failed protoblock executions using LLM to provide insights and updates protoblocks."""
    
    def __init__(self):
        self.llm_client = LLMClient()
        
    def analyze_and_update(self, execution_data: Dict) -> Tuple[str, Optional[Dict]]:
        """
        Analyze a failed execution attempt and provide insights, along with an updated protoblock if needed.
        
        Args:
            execution_data: Dictionary containing the execution data from the log file
            
        Returns:
            Tuple[str, Optional[Dict]]: Analysis text and optionally updated protoblock data
        """
        # Extract relevant information
        protoblock = execution_data['protoblock']
        git_diff = execution_data['git_diff']
        test_results = execution_data['test_results']
        
        # Get codebase content for context
        try:
            codebase = gather_python_files('.')
        except Exception as e:
            logger.error(f"Failed to gather codebase content: {e}")
            codebase = "Error gathering codebase content"
        
        # Construct prompt for LLM
        prompt = f"""Analyze this failed protoblock execution and provide insights about what went wrong. Then, propose an updated protoblock that addresses these issues.

CURRENT CODEBASE:
{codebase}

PROTOBLOCK SPECIFICATION:
Task Description: {protoblock['task_description']}
Test Specification: {protoblock['test_specification']}
Test Data Requirements: {protoblock['test_data_generation']}

IMPLEMENTATION CHANGES (Git Diff):
{git_diff}

TEST FAILURE OUTPUT:
{test_results}

Please provide:
1. A concise analysis of what went wrong
2. An updated protoblock specification in JSON format that addresses these issues. Consider:
   - Are there missing files in write_files or context_files?
   - Can the task or test specifications be more precise?
   - Should we adjust the test data requirements?

Format your response as:
ANALYSIS:
<your analysis here>

UPDATED_PROTOBLOCK:
{{
    "task": {{
        "specification": "update the task specification with your analysis insights but keep it to the point of the previous task!"
    }},
    "test": {{
        "specification": "update the test specification with your analysis insights but keep it to the point.",
        "data": "updated test data requirements",
        "replacements": []
    }},
    "write_files": "if there are new files that we need, e.g. __init__.py files, add them here,
    "context_files": "if we should be looking at additional files for context, add them here",
    "commit_message": "updated commit message"
}}"""

        messages = [
            Message(role="system", content="You are an expert code reviewer and debugging assistant. Analyze failed code executions and provide clear, actionable insights with updated protoblocks."),
            Message(role="user", content=prompt)
        ]
        
        try:
            # Get analysis and updated protoblock from LLM
            response = self.llm_client.chat_completion(messages, temperature=0.3)
            
            # Split response into analysis and updated protoblock
            parts = response.split("UPDATED_PROTOBLOCK:")
            analysis = parts[0].replace("ANALYSIS:", "").strip()
            
            # Parse updated protoblock if present
            updated_protoblock = None
            if len(parts) > 1:
                try:
                    updated_protoblock = json.loads(parts[1].strip())
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse updated protoblock JSON: {e}")
            
            return analysis, updated_protoblock
            
        except Exception as e:
            logger.error(f"Failed to get LLM analysis: {e}")
            return f"Error analyzing failure: {str(e)}", None
    
    def create_updated_protoblock(self, original_block_id: str, updated_data: Dict) -> ProtoBlockSpec:
        """
        Create a new ProtoBlockSpec with updated data while preserving the original block ID.
        
        Args:
            original_block_id: The ID of the original protoblock
            updated_data: The updated protoblock data from LLM
            
        Returns:
            ProtoBlockSpec: A new protoblock specification with updated data
        """
        return ProtoBlockSpec(
            task_specification=updated_data["task"]["specification"],
            test_specification=updated_data["test"]["specification"],
            test_data=updated_data["test"]["data"],
            write_files=updated_data["write_files"],
            context_files=updated_data.get("context_files", []),
            commit_message=updated_data.get("commit_message", "Update based on previous execution"),
            block_id=original_block_id  # Preserve the original block ID
        ) 