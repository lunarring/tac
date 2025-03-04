import json
from typing import Dict, Optional
from tac.core.llm import LLMClient, Message
from tac.protoblock import ProtoBlock
from tac.core.config import config
from tac.core.log_config import setup_logging

logger = setup_logging('tac.trusty_agents.plausibility')

class PlausibilityTestingAgent:
    """
    Checks if the implemented changes match the promised functionality by analyzing
    git diff and protoblock specifications using LLM.
    """
    
    def __init__(self):
        logger.info("Initializing PlausibilityChecker")
        self.llm_client = LLMClient(strength="strong")
        self._score_values = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
        self._min_score = config.general.minimum_plausibility_score

        logger.info("Initializing PlausibilityTestingAgent")

    def _is_score_passing(self, score: str) -> bool:
        """
        Determines if a score meets the minimum passing threshold.
        
        Args:
            score: The letter grade (A, B, C, D, or F)
            
        Returns:
            bool: True if the score meets or exceeds the minimum passing score
        """
        score_value = self._score_values.get(score.upper(), -1)
        min_score_value = self._score_values.get(self._min_score.upper(), 1)  # Default to D if invalid
        return score_value >= min_score_value

    def check(self, protoblock: ProtoBlock, git_diff: str, codebase: str) -> str:
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

Here a summary of the codebase:
<codebase>
{codebase}
</codebase>

And here the description of the task:
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

MISSING FILES:
(List all files that should have been included into the protoblock either for context or for writing)

RECOMMENDATIONS:
(List specific suggestions for improvement if needed)

PLAUSIBILITY SCORE RATING:
(answer only with one letter with the rating, where:
"A" is the best possible score
"B" is good, but not perfect because some minor things that could have been done better
"C" is acceptable, but there are some issues
"D" is the minimum passing score, not a nice implementation but it will work
"F" is failed, because the implementation is not even close to the requirements, or because it probably will not work or breaks something.)

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

            # Check if score meets minimum requirement
            is_plausible = self._is_score_passing(final_plausibility_score)
            
            return is_plausible, final_plausibility_score, response
            
        except Exception as e:
            logger.error(f"Error during plausibility check: {str(e)}", exc_info=True)
            return f"Error during plausibility check: {str(e)}" 