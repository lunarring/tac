import json
import re
from typing import Dict, Optional, Tuple
from tac.core.llm import LLMClient, Message
from tac.blocks import ProtoBlock
from tac.core.config import config
from tac.core.log_config import setup_logging
from tac.agents.trusty.base import TrustyAgent, trusty_agent
from tac.utils.file_utils import load_file_contents, format_files_for_prompt

logger = setup_logging('tac.trusty_agents.plausibility')

@trusty_agent(
    name="plausibility",
    description="A trusty agent that evaluates if the implemented changes match the promised functionality by analyzing the code diff against the task description. Assigns a star rating (0-5 stars) based on plausibility.",
    protoblock_prompt="Describe what would convince you that the changes implemented match the promised functionality, assuming you are just looking at the code diff and the task description."
)
class PlausibilityTestingAgent(TrustyAgent):
    """
    Checks if the implemented changes match the promised functionality by analyzing
    git diff and protoblock specifications using LLM.
    """

    def __init__(self):
        logger.info("Initializing PlausibilityChecker")
        self.llm_client = LLMClient(llm_type="strong")
        self._min_score = config.general.trusty_agents.minimum_plausibility_score

        logger.info("Initializing PlausibilityTestingAgent")

    def _is_score_passing(self, score: float) -> bool:
        """
        Determines if a score meets the minimum passing threshold.
        
        Args:
            score: The star rating (0.0 to 5.0 stars)
            
        Returns:
            bool: True if the score meets or exceeds the minimum passing score
        """
        return score >= self._min_score

    def _check_impl(self, protoblock: ProtoBlock, codebase: Dict[str, str], code_diff: str) -> Tuple[bool, str, str]:
        """
        Analyzes the implementation against the promised changes.
        
        Args:
            protoblock: The ProtoBlock containing task specifications
            codebase: Dictionary mapping file paths to their contents
            code_diff: The git diff showing implemented changes
            
        Returns:
            Tuple containing:
            - bool: Success status (True if check passed, False otherwise)
            - str: Error analysis (empty string if success is True)
            - str: Failure type description (empty string if success is True)
        """
        logger.info("Starting LLM-based plausibility check")
        logger.debug(f"ProtoBlock ID: {protoblock.block_id}")
        logger.debug(f"Git diff length: {len(code_diff) if code_diff else 'None'}")
        
        try:
            # Process write files
            write_files = list(set(protoblock.write_files))
            write_file_contents = load_file_contents(write_files, "write")
            write_files_prompt = format_files_for_prompt(write_file_contents)

            # Prepare prompt
            analysis_prompt = f"""<purpose>
You are a senior software engineer reviewing code changes. Your task is to determine if the implemented changes match the promised functionality and requirements. Critically, you need to determine if the implemented changes are also actively used in the codebase and integrated properly, especially when existing functionality is replaced with new one. However keep in mind, the implementation was done by a junior developer and we don't want to scare them off. Furthermore, the codebase passed all tests already, but here we are interested if the changes are making sense in what we want to achieve.
</purpose>

Here are the files that were modified:
<modified_files>
{write_files_prompt}
</modified_files>

And here specifically what was changed:
<code_diff>
{code_diff}
</code_diff>

And here the description of the task:
<protoblock>
Task Description: {protoblock.task_description}
Write Files: {protoblock.write_files}
Context Files: {protoblock.context_files}
Plausibility Prompt: {protoblock.trusty_agent_prompts.get("plausibility", "Use common sense.")}
</protoblock>



<analysis_rules>
1. Compare the implemented changes against the task description
2. Verify that the changes fulfill the promised functionality
3. Check if any changes seem unrelated or potentially harmful
4. Consider if the implementation is complete and sufficient, particularly that the new code is integrated properly into the program flow and not just isolated dead code.
5. Look for any missing requirements or incomplete implementations
6. Look if there are any external dependencies that may have been hallucinated by the junior developer.
7. Find out whether existing functionality is broken by the changes.
8. Finally, come up with a PLAUSIBILITY STAR RATING based on the analysis, where 5 stars is the best and 0 stars is failed. The minimum passing score is 3.0 stars. Your rating should be a number between 0.0 and 5.0 (can include decimal places for precision).
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

PLAUSIBILITY STAR RATING:
(Provide a numeric rating between 0.0 and 5.0 stars, where:
5.0 stars = Perfect match with requirements
4.0 stars = Good implementation with minor improvements possible
3.0 stars = Acceptable implementation with some issues
2.0 stars = Poor implementation with significant issues but partially works
1.0 stars = Very poor implementation with major issues
0.0 stars = Failed implementation that does not meet requirements at all)

HUMAN VERIFICATION:
Provide me here briefly how I can run the code myself to verify the changes. This could be for instance "python main.py" or "python -m tests.test_piano_trainer_main" or similar.
</output_format>"""

            logger.debug(f"Prompt for plausibility check: {analysis_prompt}")
            
            messages = [
                Message(role="user", content=analysis_prompt)
            ]
            
            logger.info("Plausibility check starting, sending request to LLM")
            analysis = self.llm_client.chat_completion(messages)
            
            if not analysis or not analysis.strip():
                logger.error("Received empty response from LLM")
                return False, "Error: Unable to generate plausibility analysis", "Plausibility check failed"
            
            logger.info("Successfully received LLM analysis")

            # Extract sections for UI display
            summary = ""
            if "BRIEF SUMMARY OF THE APPROACH" in analysis:
                summary_parts = analysis.split("BRIEF SUMMARY OF THE APPROACH")
                if len(summary_parts) > 1:
                    end_marker = None
                    for marker in ["DETAILED ANALYSIS:", "ROOT CAUSE:", "MISSING FILES:", "RECOMMENDATIONS:"]:
                        if marker in summary_parts[1]:
                            end_marker = marker
                            break
                    
                    if end_marker:
                        summary = summary_parts[1].split(end_marker)[0].strip()
                    else:
                        summary = summary_parts[1].strip()
                    
                    logger.info(f"Brief Summary: {summary[:100]}...")
                    
            # Store summary for UI display
            self.summary = summary

            # Extract HUMAN VERIFICATION section if present
            human_verification = ""
            if "HUMAN VERIFICATION:" in analysis:
                human_verification_parts = analysis.split("HUMAN VERIFICATION:")
                if len(human_verification_parts) > 1:
                    human_verification = human_verification_parts[1].strip()
                    logger.info(f"Human Verification: {human_verification}", heading=True)
            
            # Store verification info for UI display
            self.verification_info = human_verification

            # Extract star rating
            star_rating = 0.0
            if "PLAUSIBILITY STAR RATING:" in analysis:
                rating_section = analysis.split("PLAUSIBILITY STAR RATING:")[1].strip()
                # Extract just the numeric rating
                rating_text = ""
                for line in rating_section.split("\n"):
                    line = line.strip()
                    if line:
                        # Try to extract a number from the line
                        numbers = re.findall(r'\d+\.?\d*', line)
                        if numbers:
                            rating_text = numbers[0]
                            break
                
                try:
                    star_rating = float(rating_text)
                    # Ensure the rating is within bounds
                    star_rating = max(0.0, min(5.0, star_rating))
                except (ValueError, IndexError):
                    logger.error(f"Failed to parse star rating from: {rating_text}")
                    star_rating = 0.0
            
            # Store stars for UI display (formatted to 1 decimal place)
            self.stars = star_rating
            formatted_stars = f"{star_rating:.1f}"
            self.grade = formatted_stars
            
            # Add a field indicating the star rating scale for UI display
            self.grade_info = {
                5.0: "Excellent - Perfect match with requirements",
                4.0: "Good - Minor improvements possible", 
                3.0: "Acceptable - Some issues exist",
                2.0: "Poor - Significant issues but partially works",
                1.0: "Very poor - Major issues",
                0.0: "Failed - Does not meet requirements"
            }.get(round(star_rating), f"{formatted_stars} stars")

            # Check if score meets minimum requirement
            is_plausible = self._is_score_passing(star_rating)

            logger.info(f"Plausibility star rating: {formatted_stars}")
            
            if is_plausible:
                return True, "", ""
            else:
                return False, analysis, "Plausibility check failed"
            
        except Exception as e:
            logger.error(f"Error during plausibility check: {str(e)}", exc_info=True)
            return False, f"Error during plausibility check: {str(e)}", "Plausibility check exception" 