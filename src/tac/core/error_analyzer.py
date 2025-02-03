import logging
from typing import Optional, Dict
from tac.core.llm import LLMClient, Message
from tac.protoblock import ProtoBlock
from tac.utils.file_gatherer import gather_python_files
from tac.utils.project_files import ProjectFiles
import yaml
import os

logger = logging.getLogger(__name__)

class ErrorAnalyzer:
    """Analyzes test failures and implementation errors to provide insights using LLM"""
    
    def __init__(self):
        logger.info("Initializing ErrorAnalyzer")
        self.llm_client = LLMClient(strength="strong")
        self.project_files = ProjectFiles()

    def _load_config(self) -> dict:
        """Load configuration from config.yaml"""
        logger.info("Loading configuration from config.yaml")
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'config.yaml')
        logger.debug(f"Config path: {config_path}")
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            logger.debug(f"Loaded config: {config}")
            return config

    def _get_file_content(self, file_path: str, use_summaries: bool = False) -> str:
        """
        Get file content, either as full content or summary if enabled.
        
        Args:
            file_path: Path to the file
            use_summaries: Whether to use summaries instead of full content
            
        Returns:
            str: File content or summary
        """
        try:
            with open(file_path, 'r') as f:
                return f.read()
        except Exception as e:
            logger.warning(f"Error reading file {file_path}: {str(e)}")
            return f"Error reading file: {str(e)}"

    def analyze_failure(self, protoblock: ProtoBlock, test_results: str, codebase: Dict[str, str]) -> str:
        """
        Analyzes test failures and implementation errors using LLM.
        
        Args:
            protoblock: The ProtoBlock that failed
            test_results: The test results/error output
            codebase: Dictionary mapping file paths to their contents
            
        Returns:
            str: Detailed analysis of what went wrong and suggestions for improvement
        """
        logger.info("Starting LLM-based failure analysis")
        logger.debug(f"ProtoBlock ID: {protoblock.block_id}")
        logger.debug(f"Test results length: {len(test_results) if test_results else 'None'}")
        logger.debug(f"Codebase files to analyze: {list(codebase.keys())}")
        
        try:
            # Load config to check if summaries are enabled
            config = self._load_config()
            use_summaries = config.get('general', {}).get('use_file_summaries', False)
            logger.info(f"Using file summaries: {use_summaries}")
            
            # Format codebase for prompt
            logger.info("Formatting codebase for LLM prompt")
            codebase_content = []
            for path, content in codebase.items():
                logger.debug(f"Processing file: {path}")
                if use_summaries:
                    file_content = self._get_file_content(path, use_summaries=True)
                else:
                    file_content = content
                codebase_content.append(f"File: {path}\n```python\n{file_content}\n```")
            
            codebase_str = "\n\n".join(codebase_content)
            logger.debug(f"Formatted codebase length: {len(codebase_str)} characters")
            
            # Prepare prompt
            logger.info("Preparing LLM prompt")
            analysis_prompt = f"""<purpose>
You are a senior python software engineer analyzing a failed implementation attempt. Your goal is to provide a clear and detailed analysis of what went wrong and suggest specific improvements.
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
2. Locate the specific files and lines where errors occurred
3. Analyze the root cause - what specifically went wrong?
4. Consider if the error relates to:
   - Implementation mistakes
   - Missing dependencies or imports
   - Incorrect test assumptions
   - Environment/configuration issues
5. Suggest specific improvements or fixes
</analysis_rules>

<output_format>
Provide your analysis in the following structure:

FAILURE TYPE:
(Describe the category of failure)

ERROR LOCATION:
(Identify specific files/lines where errors occurred)

ROOT CAUSE:
(Explain the fundamental issue that caused the failure)

DETAILED ANALYSIS:
(Provide in-depth analysis of what went wrong)

RECOMMENDATIONS:
(List specific suggestions for fixing the issues)

MISSING WRITE FILES:
(Provide a list of files that the were previously not listed in Write Files of the protoblock above, but the coder needs write access to them. The format should be a list, e.g. ["tests/test_piano_trainer_main.py"])
</output_format>"""

            logger.debug(f"Prompt length: {len(analysis_prompt)} characters")
            
            messages = [
                Message(role="system", content="You are a coding assistant specialized in analyzing test failures and implementation errors. Provide clear, actionable analysis."),
                Message(role="user", content=analysis_prompt)
            ]
            
            logger.info("Sending request to LLM")
            response = self.llm_client.chat_completion(messages)
            
            if not response or not response.strip():
                logger.error("Received empty response from LLM")
                return "Error: Unable to generate analysis"
                
            logger.info("Successfully received LLM response")
            logger.debug(f"LLM response length: {len(response)} characters")
            logger.debug(f"Analysis response:\n{response}")
            
            return response
            
        except Exception as e:
            logger.error(f"Error during LLM failure analysis: {str(e)}", exc_info=True)
            return f"Error analyzing failure: {str(e)}" 