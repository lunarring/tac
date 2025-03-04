import logging
from typing import Optional, Dict
from tac.core.llm import LLMClient, Message
from tac.protoblock import ProtoBlock
from tac.utils.file_gatherer import gather_python_files
from tac.utils.project_files import ProjectFiles
from tac.core.config import config

logger = logging.getLogger(__name__)

class ErrorAnalyzer:
    """Analyzes test failures and implementation errors to provide insights using LLM"""
    
    def __init__(self):
        logger.info("Initializing ErrorAnalyzer")
        self.llm_client = LLMClient(strength="strong")
        self.project_files = ProjectFiles()

    def analyze_failure(self, protoblock: ProtoBlock, test_results: str, codebase: Dict[str, str]) -> str:
        """
        Analyzes test failures and implementation errors using LLM.
        
        Args:
            protoblock: The ProtoBlock that failed
            test_results: The test results/error output
            codebase: Dictionary mapping file paths to their contents or string content
            
        Returns:
            str: Detailed analysis of what went wrong and suggestions for improvement
        """
        logger.info("Starting LLM-based failure analysis")
        logger.debug(f"ProtoBlock ID: {protoblock.block_id}")
        logger.debug(f"Test results length: {len(test_results) if test_results else 'None'}")
        
        try:
            # Use centralized config
            use_summaries = config.general.use_file_summaries
            logger.info(f"Using file summaries: {use_summaries}")
            
            # Format codebase for prompt
            logger.info("Formatting codebase for LLM prompt")
            codebase_content = []
            
            # Handle string codebase
            if isinstance(codebase, str):
                codebase_content.append(f"Codebase Content:\n```python\n{codebase}\n```")
            else:
                # Handle dictionary codebase
                logger.debug(f"Codebase files to analyze: {list(codebase.keys())}")
                for path, content in codebase.items():
                    logger.debug(f"Processing file: {path}")
                    if use_summaries:
                        # Use existing summaries instead of generating new ones
                        summary = self.project_files._load_existing_summaries().get(path, {}).get('summary')
                        if summary:
                            file_content = f"File Summary:\n{summary}"
                        else:
                            file_content = content
                    else:
                        file_content = content
                    codebase_content.append(f"File: {path}\n```python\n{file_content}\n```")
            
            codebase_str = "\n\n".join(codebase_content)
            logger.debug(f"Formatted codebase length: {len(codebase_str)} characters")
            
            # Prepare prompt
            analysis_prompt = f"""<purpose>
You are a senior python software engineer analyzing a failed implementation attempt. Your goal is to provide a clear and detailed analysis of what went wrong and suggest specific improvements. The information for the junior software engineer who failed at their attempt is given in the <protoblock> section, the codebase in <codebase_str>, the test results in <test_results>. Your concrete analysis rules are given in <analysis_rules>.
</purpose>

<codebase_state>
{codebase_str}
</codebase_state>

<protoblock>
Task Description: {protoblock.task_description}
Test Specification: {protoblock.test_specification}
Test Data: {protoblock.test_data_generation}
Write Files: {protoblock.write_files}
Context Files: {protoblock.context_files}
</protoblock>

<test_results>
{test_results}
</test_results>

<analysis_rules>
1. First identify the type of failure (syntax error, runtime error, test assertion, etc.)
2. Gather understanding whether the error is due to an already existing test, that needs to be updated, because the protoblock makes it necessary to change existing tests.
3. In case the error is due to an already existing test, that needs to be updated, provide a detailed description of how to update the test.
4. In case the error is due to a missing file, list the files that need to be created.
5. In case the error is due to a missing import, list the imports that need to be added.
</analysis_rules>

<output_format>
Provide your analysis in the following structure:

NEW STRATEGY FOR SOLVING THE TASK:
(In more detail describe how the next implementation attempt should look like based on whst you learned from the previois attempt.)

MISSING WRITE FILES:
(so far it was possible to modify these files: {protoblock.write_files}. However, given youn analysis, do we need to edit more files? If there are files missing, directly mention them here in a list, without any additional text e.g. your reply is ["tests/test_piano_trainer_main.py"])
</output_format>"""

            messages = [
                Message(role="system", content="You are a coding assistant specialized in analyzing test failures and implementation errors. Provide clear, actionable analysis."),
                Message(role="user", content=analysis_prompt)
            ]
            
            response = self.llm_client.chat_completion(messages)
            
            if not response or not response.strip():
                logger.error("Received empty response from LLM")
                return "Error: Unable to generate analysis"
                
            return response
            
        except Exception as e:
            logger.error(f"Error during LLM failure analysis: {str(e)}", exc_info=True)
            return f"Error analyzing failure: {str(e)}" 