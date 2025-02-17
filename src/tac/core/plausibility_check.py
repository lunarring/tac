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

    def check(self, protoblock: ProtoBlock, git_diff: str) -> str:
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
You are a senior software engineer reviewing code changes. Your task is to determine if the implemented changes match the promised functionality and requirements. Critically, you need to determine if the implemented changes are also actively used in the codebase and integrated properly, especially when existing functionality is replaced with new one. However keep in mind, the implementation was done by a junior developer and we don't want to scare them off.
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
4. Consider if the implementation is complete and sufficient, particularly that the new code is integrated properly into the program flow and not just isolated dead code.
5. Look for any missing requirements or incomplete implementations
6. Look if there are any external dependencies that may have been hallucinated by the junior developer.
7. Find out whether existing functionality is broken by the changes.
8. Finally, come up with a PLAUSIBILITY SCORE RATING based on the analysis, where "A" is the best and "F" is failed. Passmark is "D". Thus the valid responses are "A", "B", "C", "D", "F".
</analysis_rules>

<output_format>
Provide your analysis in the following format:

BRIEF SUMMARY OF THE APPROACH
(Provide a brief summary of the approach taken to implement the changes)

DETAILED ANALYSIS:
(Provide in-depth analysis of what matches or mismatches with requirements)

ROOT CAUSE:
(If implausible, explain the fundamental issues)

RECOMMENDATIONS:
(List specific suggestions for improvement if needed)

PLAUSIBILITY SCORE RATING:
(answer only with one letter with the rating, where "A" is the best and "F" is failed. Passmark is "D". Thus the valid responses are "A", "B", "C", "D", "F")

</output_format>"""

            logger.debug(f"Prompt for plausibility check: {analysis_prompt}")
            
            messages = [
                Message(role="system", content="You are a coding assistant specialized in reviewing code changes for correctness and completeness. Provide clear, actionable analysis."),
                Message(role="user", content=analysis_prompt)
            ]
            
            logger.info("Plausibility check starting, sending request to LLM")
            response = self.llm_client.chat_completion(messages)
            
            if not response or not response.strip():
                logger.error("Received empty response from LLM")
                return "Error: Unable to generate plausibility analysis"
            
            logger.info("Successfully received LLM response")
            logger.debug(f"LLM response:\n{response}")

            final_plausibility_score = ""
            if "PLAUSIBILITY SCORE RATING:" in response:
                score_section = response.split("PLAUSIBILITY SCORE RATING:")[1].strip()
                # Extract just the letter grade, ignoring any additional text
                for char in score_section:
                    if char in "ABCDF":
                        final_plausibility_score = char
                        break
            
            # Strip any whitespace and ensure uppercase
            final_plausibility_score = final_plausibility_score.strip().upper()

            # A through D are considered passing grades
            is_plausible = final_plausibility_score in ["A", "B", "C", "D"]
            
            return is_plausible, final_plausibility_score
            
        except Exception as e:
            logger.error(f"Error during plausibility check: {str(e)}", exc_info=True)
            return f"Error during plausibility check: {str(e)}" 