import json
from typing import Dict, Optional, Tuple, Union
from tac.core.llm import LLMClient, Message
from tac.blocks import ProtoBlock
from tac.core.config import config
from tac.core.log_config import setup_logging
from tac.agents.trusty.base import TrustyAgent, trusty_agent
from tac.agents.trusty.results import TrustyAgentResult
from tac.utils.file_utils import load_file_contents, format_files_for_prompt

logger = setup_logging('tac.trusty_agents.code_reviewer')

@trusty_agent(
    name="code_reviewer",
    description="A trusty agent that evaluates if the implemented changes match the promised functionality by analyzing the code diff against the task description. Assigns a letter grade (A-F) based on code review.",
    protoblock_prompt="Describe what would convince you that the changes implemented match the promised functionality, assuming you are just looking at the code diff and the task description.",
    llm="o3-mini",
    mandatory=True
)
class CodeReviewerTestingAgent(TrustyAgent):
    """
    Checks if the implemented changes match the promised functionality by analyzing
    git diff and protoblock specifications using LLM.
    """

    def __init__(self):
        logger.info("Initializing CodeReviewerChecker")
        self.llm_client = LLMClient(component="code_reviewer")
        self._score_values = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
        self._min_score = config.general.trusty_agents.minimum_code_review_score

        logger.info("Initializing CodeReviewerTestingAgent")

    def _is_score_passing(self, score: str) -> bool:
        """
        Determines if a score meets the minimum passing threshold.
        
        Args:
            score: The letter grade (A, B, C, D, or F)
            
        Returns:
            bool: True if the score meets or exceeds the minimum passing score
        """
        score_value = self._score_values.get(score.upper(), -1)
        min_score_value = self._score_values.get(config.general.trusty_agents.minimum_code_review_score.upper(), 1)  # Default to D if invalid
        return score_value >= min_score_value

    def _check_impl(self, protoblock: ProtoBlock, codebase: Dict[str, str], code_diff: str) -> Union[Tuple[bool, str, str], TrustyAgentResult]:
        """
        Analyzes the implementation against the promised changes.
        
        Args:
            protoblock: The ProtoBlock containing task specifications
            codebase: Dictionary mapping file paths to their contents
            code_diff: The git diff showing implemented changes
            
        Returns:
            TrustyAgentResult: Result object with code review analysis and grade
        """
        # Create a result object for this agent
        result = TrustyAgentResult(
            success=False,  # Default to False, will set to True if passing
            agent_type="code_reviewer",
            summary="Checking code review of implementation"
        )
        
        logger.info("Starting LLM-based code review check")
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

We want to achieve the following task description: {protoblock.task_description}

Here are all the changes that were made by the junior developer. This is the most important place for your evaluation, do these changes in code_diff make sense? Do they fulfill the task description? Are they aligned with the task description?
<code_diff>
{code_diff}
</code_diff>

For context, here are the full files that the junior developer had access to.
<modified_files>
{write_files_prompt}
</modified_files>


<analysis_rules>
1. Compare the implemented changes against the task description, looking at the <code_diff> section, because these are the changes.
2. Verify that the changes in <code_diff> fulfill the promised functionality in the task description.
3. Check if any changes in <code_diff> seem unrelated, unwanted or potentially harmful
4. Consider if the implementation is complete and sufficient, particularly that the new code is integrated properly into the program flow and not just isolated dead code.
5. Look for any missing requirements or incomplete implementations
6. Look if there are any external dependencies that may have been hallucinated by the junior developer.
7. Find out whether existing functionality is broken by the changes.
8. Finally, come up with a CODE REVIEW SCORE RATING based on the analysis, where "A" is the best and "F" is failed. Passmark is "D". Thus the valid responses are "A", "B", "C", "D", "F".
</analysis_rules>

For the output, please follow the following format. Please use markdown formatting, at least for the headings.
<output_format>
## BRIEF SUMMARY OF THE APPROACH
(Provide a brief summary of the approach taken to implement the changes)

## ALIGNMENT OF IMPLEMENTED CHANGES WITH TASK DESCRIPTION
(How well does the implemented changes align with the task description? Do they fulfill the task description? Are they aligned with the task description?)

## UNEXPECTED CHANGES
(List any unexpected changes that we did not expect, or are not aligned with the task description. Cross-check the changes in the <code_diff> section with the task description and list everything unrelated here)

## RATING
(How would appropriate would you rate the code changes, on a scale of A to F? A is the best, F is the worst. 
Your responsibility is to FAIL the test (D or F) if one of two conditions is met: 
-the changes are not accurate with regards to the expected changes
-there are ANY unexpected changes that we did not expect
ONLY RETURN HERE A SINGLE LETTER, A, B, C, D, F)

## OUT OF SCOPE REPORT
(Report here if the expected changes are out of scope of what you can do to judge, given the <code_diff> section)

## RECOMMENDATIONS
(Provide recommendations for the junior developer to improve the implementation)

## HUMAN VERIFICATION
Provide me here briefly how I can run the code myself to verify the changes. This could be for instance "python main.py" or "python -m tests.test_piano_trainer_main" or similar.

## MISSING FILES
(List all files that you think should have been available to implement the desired changes, but were not present in the <modified_files> section)
</output_format>"""

            logger.debug(f"Prompt for code review check: {analysis_prompt}")
            
            messages = [
                Message(role="user", content=analysis_prompt)
            ]
            
            logger.info("Code review check starting, sending request to LLM")
            analysis = self.llm_client.chat_completion(messages)
            
            if not analysis or not analysis.strip():
                logger.error("Received empty response from LLM")
                result.summary = "Error: Unable to generate code review analysis"
                result.add_error("Received empty response from LLM", "Analysis failed")
                return result
            
            logger.info("Successfully received LLM analysis")

            # Add full analysis to result
            result.add_report(analysis, "Full Analysis")

            # Extract sections for result sections
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
                    
                    # Add summary to result details
                    result.details["summary"] = summary

            # Extract HUMAN VERIFICATION section if present
            human_verification = ""
            if "HUMAN VERIFICATION:" in analysis:
                human_verification_parts = analysis.split("HUMAN VERIFICATION:")
                if len(human_verification_parts) > 1:
                    human_verification = human_verification_parts[1].strip()
                    logger.info(f"Human Verification: {human_verification}", heading=True)
                    
                    # Add verification info to result details
                    result.details["verification_info"] = human_verification

            # Extract missing files section if present
            missing_files = ""
            if "MISSING FILES:" in analysis:
                missing_files_parts = analysis.split("MISSING FILES:")
                if len(missing_files_parts) > 1:
                    end_marker = None
                    for marker in ["RECOMMENDATIONS:", "RATING:", "HUMAN VERIFICATION:"]:
                        if marker in missing_files_parts[1]:
                            end_marker = marker
                            break
                    
                    if end_marker:
                        missing_files = missing_files_parts[1].split(end_marker)[0].strip()
                    else:
                        missing_files = missing_files_parts[1].strip()
                    
                    # Add missing files to result details
                    result.details["missing_files"] = missing_files

            # Extract code review score
            final_code_review_score = ""
            if "## RATING" in analysis:
                score_section = analysis.split("## RATING")[1].strip()
                # Extract just the letter grade, ignoring any additional text
                for char in score_section:
                    if char in "ABCDF":
                        final_code_review_score = char
                        break
            
            # Strip any whitespace and ensure uppercase
            final_code_review_score = final_code_review_score.strip().upper()
            
            # Add grade to result
            if final_code_review_score in ["A", "B", "C", "D", "F"]:
                grade_descriptions = {
                    "A": "Excellent - Perfect match with requirements",
                    "B": "Good - Minor issues but overall solid implementation",
                    "C": "Acceptable - Has issues but generally meets requirements",
                    "D": "Minimum Pass - Barely meets requirements",
                    "F": "Failed - Does not meet requirements"
                }
                
                result.add_grade(
                    final_code_review_score, 
                    "A-F", 
                    grade_descriptions.get(final_code_review_score, "")
                )
                
                # Store grade in details for backward compatibility
                result.details["grade"] = final_code_review_score
                result.details["grade_info"] = grade_descriptions
            else:
                logger.warning("Invalid grade extracted, no letter grade found")
                result.add_error("Invalid grade extracted", "Grade parsing failed")
                return result
            
            # Check if the score passes the minimum requirement
            is_passing = self._is_score_passing(final_code_review_score)
            
            # Update result success status and summary
            if is_passing:
                result.success = True
                result.summary = f"Code review check passed with grade {final_code_review_score}"
            else:
                result.success = False
                result.summary = f"Code review check failed with grade {final_code_review_score} (minimum: {self._min_score})"
            
            return result
            
        except Exception as e:
            logger.exception(f"Error in code review check: {str(e)}")
            result.success = False
            result.summary = "Code review check failed with error"
            result.add_error(str(e), "Code review check error", logger.format_exc() if hasattr(logger, 'format_exc') else None)
            return result 

    def should_run_mandatory(self, protoblock: ProtoBlock, codebase: Dict[str, str]) -> Tuple[bool, str]:
        """
        Code reviewer agent should always run as a mandatory agent.
        
        Args:
            protoblock: The ProtoBlock containing task specifications
            codebase: Dictionary mapping file paths to their contents
            
        Returns:
            Tuple containing:
            - bool: Always True for code reviewer agent
            - str: Reason for the decision
        """
        return True, "Code reviewer agent always runs to ensure code changes match task description" 