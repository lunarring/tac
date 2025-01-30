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
    """Analyzes test failures and implementation errors to provide insights"""
    
    def __init__(self):
        self.llm_client = LLMClient(strength="strong")
        self.project_files = ProjectFiles()

    def _load_config(self) -> dict:
        """Load configuration from config.yaml"""
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'config.yaml')
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)

    def _get_file_content(self, file_path: str, use_summaries: bool = False) -> str:
        """
        Get file content, either as full content or summary if enabled.
        
        Args:
            file_path: Path to the file
            use_summaries: Whether to use summaries instead of full content
            
        Returns:
            str: File content or summary
        """
        if not use_summaries:
            with open(file_path, 'r') as f:
                return f.read()
                
        # Try to get summary from cache
        summary = self.project_files.get_file_summary(file_path)
        if summary:
            if "error" in summary:
                logger.warning(f"Error in cached summary for {file_path}: {summary['error']}")
                return f"Error analyzing file: {summary['error']}"
            return f"File Summary:\n{summary['summary']}"
            
        # Generate new summary if not cached
        logger.info(f"Generating new summary for {file_path}")
        stats = self.project_files.update_summaries(exclusions=[".git", "__pycache__"])
        logger.debug(f"Summary update stats: {stats}")
        
        # Try to get summary again
        summary = self.project_files.get_file_summary(file_path)
        if summary:
            if "error" in summary:
                return f"Error analyzing file: {summary['error']}"
            return f"File Summary:\n{summary['summary']}"
            
        return f"Error: Could not generate summary for {file_path}"

    def analyze_failure(self, protoblock: ProtoBlock, test_results: str, codebase: Dict[str, str]) -> str:
        """
        Analyzes test failures and implementation errors to provide insights.
        
        Args:
            protoblock: The ProtoBlock that failed
            test_results: The test results/error output
            codebase: Dictionary mapping file paths to their contents
            
        Returns:
            str: Detailed analysis of what went wrong and suggestions for improvement
        """
        # Load config to check if summaries are enabled
        config = self._load_config()
        use_summaries = config.get('general', {}).get('use_file_summaries', False)
        
        # Format codebase for prompt, using summaries if enabled
        codebase_content = []
        for path, content in codebase.items():
            if use_summaries:
                file_content = self._get_file_content(path, use_summaries=True)
                codebase_content.append(f"File: {path}\n{file_content}")
            else:
                codebase_content.append(f"File: {path}\n```python\n{content}\n```")
        
        codebase_str = "\n\n".join(codebase_content)
        
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

        messages = [
            Message(role="system", content="You are a coding assistant specialized in analyzing test failures and implementation errors. Provide clear, actionable analysis."),
            Message(role="user", content=analysis_prompt)
        ]
        
        try:
            response = self.llm_client.chat_completion(messages)
            if not response or not response.strip():
                return "Error: Unable to generate analysis"
                
            logger.debug(f"Error analysis response:\n{response}")
            return response
            
        except Exception as e:
            logger.error(f"Error during failure analysis: {str(e)}")
            return f"Error analyzing failure: {str(e)}" 