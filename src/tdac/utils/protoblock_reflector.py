from typing import Dict, Optional
import logging
from tdac.core.llm import LLMClient, Message

logger = logging.getLogger(__name__)

class ProtoBlockReflector:
    """Analyzes failed protoblock executions using LLM to provide insights."""
    
    def __init__(self):
        self.llm_client = LLMClient()
        
    def analyze_failure(self, execution_data: Dict) -> str:
        """
        Analyze a failed execution attempt and provide insights.
        
        Args:
            execution_data: Dictionary containing the execution data from the log file
            
        Returns:
            str: Analysis and insights about the failure
        """
        # Extract relevant information
        protoblock = execution_data['protoblock']
        git_diff = execution_data['git_diff']
        test_results = execution_data['test_results']
        
        # Construct prompt for LLM
        prompt = f"""Analyze this failed protoblock execution and provide insights about what went wrong and potential improvements.

PROTOBLOCK SPECIFICATION:
Task Description: {protoblock['task_description']}
Test Specification: {protoblock['test_specification']}
Test Data Requirements: {protoblock['test_data_generation']}

IMPLEMENTATION CHANGES (Git Diff):
{git_diff}

TEST FAILURE OUTPUT:
{test_results}

Please provide a concise analysis covering:
1. What approach was taken in the implementation
2. Why the tests failed (root cause analysis)
3. What could be improved in the next attempt
4. Any potential issues in the test specifications themselves

Keep your response focused and actionable."""

        messages = [
            Message(role="system", content="You are an expert code reviewer and debugging assistant. Analyze failed code executions and provide clear, actionable insights."),
            Message(role="user", content=prompt)
        ]
        
        try:
            # Get analysis from LLM
            response = self.llm_client.chat_completion(messages, temperature=0.3)  # Lower temperature for more focused analysis
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Failed to get LLM analysis: {e}")
            return f"Error analyzing failure: {str(e)}" 