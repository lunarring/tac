import logging
import json
from typing import Dict, Optional
from tac.core.llm import LLMClient, Message
from tac.protoblock import ProtoBlock

logger = logging.getLogger(__name__)

class PlausibilityChecker:
    """
    Checks if the implemented changes match the promised functionality by analyzing
    git diff and protoblock specifications using LLM.
    """
    
    def __init__(self):
        logger.info("Initializing PlausibilityChecker")
        self.llm_client = LLMClient(strength="strong")

    def check_implementation(self, protoblock: ProtoBlock, git_diff: str) -> str:
        """
        Analyzes the implementation against the promised changes.
        
        Args:
            protoblock: The ProtoBlock containing task specifications
            git_diff: The git diff showing implemented changes
            
        Returns:
            str: Formatted analysis string containing correctness and reasoning
        """
        logger.info("Starting LLM-based plausibility check")
        logger.debug(f"ProtoBlock ID: {protoblock.block_id}")
        logger.debug(f"Git diff length: {len(git_diff) if git_diff else 'None'}")
        
        try:
            # Prepare prompt
            analysis_prompt = f"""<purpose>
You are a senior software engineer reviewing code changes. Your task is to determine if the implemented changes match the promised functionality and requirements. However you don't need to be overly strict, as the implementation was done by a very junior developer and we don't want to scare them off. If the program sort of works, that's good enough.
</purpose>

<protoblock>
Task Description: {protoblock.task_description}
Test Specification: {protoblock.test_specification}
Write Files: {protoblock.write_files}
Context Files: {protoblock.context_files}
</protoblock>

<implemented_changes>
{git_diff}
</implemented_changes>

<analysis_rules>
1. Compare the implemented changes against the task description
2. Verify that the changes fulfill the promised functionality
3. Check if any changes seem unrelated or potentially harmful
4. Consider if the implementation is complete and sufficient
5. Look for any missing requirements or incomplete implementations
</analysis_rules>

<output_format>
Provide your analysis in the following format:

DETAILED ANALYSIS:
(Provide in-depth analysis of what matches or mismatches with requirements)

ROOT CAUSE:
(If implausible, explain the fundamental issues)

RECOMMENDATIONS:
(List specific suggestions for improvement if needed)

FINAL PLAUSIBILITY:
(answer only with one word "OK" or "BAD" here)

</output_format>"""

            logger.debug(f"Prompt length: {len(analysis_prompt)} characters")
            
            messages = [
                Message(role="system", content="You are a coding assistant specialized in reviewing code changes for correctness and completeness. Provide clear, actionable analysis."),
                Message(role="user", content=analysis_prompt)
            ]
            
            logger.info("Sending request to LLM")
            response = self.llm_client.chat_completion(messages)
            
            if not response or not response.strip():
                logger.error("Received empty response from LLM")
                return "Error: Unable to generate plausibility analysis"
            
            logger.info("Successfully received LLM response")
            logger.debug(f"LLM response:\n{response}")
            
            return response
            
        except Exception as e:
            logger.error(f"Error during plausibility check: {str(e)}", exc_info=True)
            return f"Error during plausibility check: {str(e)}" 