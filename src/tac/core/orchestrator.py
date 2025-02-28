import logging
import json
from typing import Dict, List, Optional, Any
from tac.core.llm import LLMClient, Message
from tac.core.config import config

logger = logging.getLogger(__name__)


class ChunkingResult:
    """
    Represents the complete result of a task chunking operation.
    """
    def __init__(self, 
                 chunks: List[str], 
                 branch_name: str, 
                 analysis: str = None,
                 strategy: str = None,
                 num_chunks: int = None,
                 raw_data: Dict[str, Any] = None):
        self.chunks = chunks
        self.branch_name = branch_name
        self.analysis = analysis
        self.strategy = strategy or analysis  # Use strategy if provided, otherwise fall back to analysis
        self.num_chunks = num_chunks or len(chunks)
        self.raw_data = raw_data or {}
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert the chunking result to a dictionary representation."""
        return {
            "branch_name": self.branch_name,
            "analysis": self.analysis,
            "strategy": self.strategy,
            "num_chunks": self.num_chunks,
            "chunks": self.chunks,
            "raw_data": self.raw_data
        }
    
    def get_chunk_titles(self) -> List[str]:
        """Extract titles from chunks."""
        titles = []
        for chunk in self.chunks:
            for line in chunk.split('\n'):
                if line.startswith("# "):
                    titles.append(line[2:])
                    break
            else:
                titles.append(f"Chunk {len(titles)+1}")
        return titles
        
    def get_commit_messages(self) -> List[str]:
        """Generate commit messages for each chunk."""
        titles = self.get_chunk_titles()
        return [f"Implement {title}" for title in titles]


class TaskChunker:
    """
    Uses an LLM to intelligently split task instructions into appropriate chunks
    based on complexity, dependencies, and logical separation.
    """
    
    def __init__(self):
        logger.info("Initializing TaskChunker")
        self.llm_client = LLMClient(strength="strong")
    
    def chunk(self, task_instructions: str, codebase: str) -> ChunkingResult:
        """
        Analyzes the task instructions and splits them into appropriate chunks.
        
        Args:
            task_instructions: The full task instructions to be split
            codebase: A summary of the codebase for context
            
        Returns:
            ChunkingResult: A structured result containing all chunks and metadata
        """
        logger.info("Starting LLM-based task chunking")
        logger.debug(f"Task instructions length: {len(task_instructions)}")
        
        try:
            # Prepare prompt
            chunking_prompt = f"""<purpose>
You are a senior software engineer tasked with breaking down a complex programming task into smaller, manageable chunks. Your goal is to analyze the task instructions and determine the optimal way to split them into separate sub-tasks that can be implemented independently or in sequence.
</purpose>

Here is a summary of the codebase:
<codebase>
{codebase}
</codebase>

Here are the full task instructions:
<task_instructions>
{task_instructions}
</task_instructions>

<chunking_rules>
1. Analyze the complexity and scope of the task
2. Identify logical boundaries where the task can be split
3. Consider dependencies between different parts of the task
4. Ensure each chunk is self-contained and can be reasonably implemented
5. Prioritize chunks based on dependencies (what needs to be done first)
6. Keep the number of chunks reasonable (typically 1-10 chunks, depending on complexity)
7. For simple tasks, it's perfectly acceptable to have just 1 chunk
8. For very complex tasks, don't exceed 10 chunks to maintain manageability
9. Create a single descriptive git branch name for the ENTIRE task (lowercase with hyphens, no spaces)
   - This branch name should be prefixed with 'tac/feature/' (e.g., 'tac/feature/add-user-authentication')
   - The branch name should be descriptive of the overall task, not individual chunks
10. Each chunk should include its own tests where appropriate - no separate integration test is needed
</chunking_rules>

<output_format>
Provide your analysis in the following JSON format:

```json
{{
  "strategy": "Explain briefly what you did, and why you go for this chunking strategy",
  "branch_name": "tac/feature/descriptive-git-branch-name-for-entire-task",
  "chunks": [
    {{
      "title": "Short descriptive title for chunk 1",
      "description": "Detailed description of what should be implemented in this chunk, including any necessary tests, write one long description text without any formatting or line breaks."
    }},
    ...additional chunks...
  ]
}}
```
</output_format>"""

            logger.debug(f"Prompt for task chunking: {chunking_prompt}")
            
            messages = [
                Message(role="system", content="You are a coding assistant specialized in breaking down complex programming tasks into manageable chunks. Provide clear, actionable task divisions."),
                Message(role="user", content=chunking_prompt)
            ]
            
            logger.info("Task chunking starting, sending request to LLM")
            response = self.llm_client.chat_completion(messages)
            
            if not response or not response.strip():
                logger.error("Received empty response from LLM")
                return self._create_default_result(task_instructions)
            
            logger.info("Successfully received LLM response")
            logger.debug(f"LLM response:\n{response}")

            # Extract JSON from response
            json_content = self._extract_json(response)
            if not json_content:
                logger.warning("Could not extract valid JSON from LLM response, returning original as single chunk")
                return self._create_default_result(task_instructions)
                
            try:
                chunk_data = json.loads(json_content)
                
                # Validate the structure
                if not isinstance(chunk_data, dict) or "chunks" not in chunk_data or not isinstance(chunk_data["chunks"], list):
                    logger.warning("Invalid chunk data structure, returning original as single chunk")
                    return self._create_default_result(task_instructions)
                
                # Get the branch name for the entire task
                branch_name = None
                if "branch_name" in chunk_data and chunk_data["branch_name"]:
                    branch_name = chunk_data["branch_name"]
                    # Ensure branch name has the correct prefix
                    if not branch_name.startswith("tac/"):
                        branch_name = f"tac/feature/{branch_name.replace('tac/feature/', '')}"
                else:
                    # Create a default branch name based on the task
                    words = task_instructions.split()[:5]
                    feature_name = "-".join([w.lower() for w in words if w.isalnum()])
                    if not feature_name:
                        feature_name = "task-implementation"
                    branch_name = f"tac/feature/{feature_name}"
                
                logger.info(f"Using branch name for all chunks: {branch_name}")
                
                # Extract the chunk descriptions
                chunks = []
                for chunk in chunk_data["chunks"]:
                    if "title" in chunk and "description" in chunk:
                        chunk_text = f"# {chunk['title']}\n\n{chunk['description']}"
                        
                        # Add dependencies if present
                        if "dependencies" in chunk and chunk["dependencies"]:
                            dependencies = ", ".join(chunk["dependencies"])
                            chunk_text += f"\n\nDependencies: {dependencies}"
                        
                        # Add the same branch name to all chunks
                        chunk_text += f"\n\nGit Branch: {branch_name}"
                            
                        chunks.append(chunk_text)
                
                if not chunks:
                    logger.warning("No valid chunks found, returning original as single chunk")
                    return self._create_default_result(task_instructions)
                
                # Create and return the ChunkingResult
                analysis = chunk_data.get("analysis", "Task chunked successfully")
                strategy = chunk_data.get("strategy", analysis)
                num_chunks = chunk_data.get("num_chunks", len(chunks))
                
                result = ChunkingResult(
                    chunks=chunks,
                    branch_name=branch_name,
                    analysis=analysis,
                    strategy=strategy,
                    num_chunks=num_chunks,
                    raw_data=chunk_data
                )
                    
                logger.info(f"Successfully chunked task into {len(chunks)} parts")
                return result
                
            except json.JSONDecodeError as e:
                logger.error(f"Error decoding JSON from LLM response: {str(e)}")
                return self._create_default_result(task_instructions)
                
        except Exception as e:
            logger.error(f"Error during task chunking: {str(e)}", exc_info=True)
            return self._create_default_result(task_instructions)
    
    def _create_default_result(self, task_instructions: str) -> ChunkingResult:
        """
        Creates a default ChunkingResult with a single chunk containing the original task.
        
        Args:
            task_instructions: The original task instructions
            
        Returns:
            ChunkingResult: A default chunking result with one chunk
        """
        # Create a default branch name
        words = task_instructions.split()[:5]
        feature_name = "-".join([w.lower() for w in words if w.isalnum()])
        if not feature_name:
            feature_name = "task-implementation"
        branch_name = f"tac/feature/{feature_name}"
        
        # Create a single chunk with the original task
        chunk_text = f"# Complete Task Implementation\n\n{task_instructions}\n\nGit Branch: {branch_name}"
        
        # Create and return the result
        return ChunkingResult(
            chunks=[chunk_text],
            branch_name=branch_name,
            analysis="Task was not chunked due to processing error or invalid response",
            strategy="Task was not chunked due to processing error or invalid response",
            num_chunks=1,
            raw_data={"error": "Failed to process task chunking"}
        )
    
    def _extract_json(self, text: str) -> Optional[str]:
        """
        Extracts JSON content from the LLM response.
        
        Args:
            text: The full text response from the LLM
            
        Returns:
            Optional[str]: The extracted JSON string, or None if not found
        """
        # Look for JSON content between triple backticks
        if "```json" in text and "```" in text.split("```json", 1)[1]:
            return text.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in text and "```" in text.split("```", 1)[1]:
            # Try without the json specifier
            return text.split("```", 1)[1].split("```", 1)[0].strip()
        
        # If no code blocks, try to find JSON-like content with curly braces
        if "{" in text and "}" in text:
            start_idx = text.find("{")
            # Find the matching closing brace
            open_count = 0
            for i in range(start_idx, len(text)):
                if text[i] == "{":
                    open_count += 1
                elif text[i] == "}":
                    open_count -= 1
                    if open_count == 0:
                        return text[start_idx:i+1]
        
        return None