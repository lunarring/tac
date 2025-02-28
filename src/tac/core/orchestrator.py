import logging
import json
from typing import Dict, List, Optional, Any
from tac.core.llm import LLMClient, Message
from tac.core.config import config

logger = logging.getLogger(__name__)


class Chunk:
    """
    Represents a single chunk of a task to be implemented.
    """
    def __init__(self, 
                 title: str, 
                 description: str, 
                 branch_name: str,
                 dependencies: List[str] = None):
        self.title = title
        self.description = description
        self.branch_name = branch_name
        self.dependencies = dependencies or []
        
    @classmethod
    def from_text(cls, text: str) -> 'Chunk':
        """
        Create a Chunk object from a text representation.
        
        Args:
            text: The text representation of the chunk
            
        Returns:
            Chunk: A new Chunk object
        """
        title = "Untitled Chunk"
        description_lines = []
        branch_name = None
        dependencies = []
        
        # Parse the text to extract title, description, and branch name
        lines = text.split('\n')
        in_description = False
        skip_empty_lines = True
        
        for line in lines:
            if line.startswith("# "):
                title = line[2:].strip()
                skip_empty_lines = True  # Skip empty lines after title
            elif line.startswith("Git Branch:"):
                branch_name = line.replace("Git Branch:", "").strip()
            elif line.startswith("Dependencies:"):
                deps = line.replace("Dependencies:", "").strip()
                dependencies = [d.strip() for d in deps.split(",")]
            elif not line.strip() and skip_empty_lines:
                # Skip empty lines after title or at the beginning
                continue
            else:
                skip_empty_lines = False  # Stop skipping empty lines once we have content
                description_lines.append(line)
        
        # Join the description lines
        description = '\n'.join(description_lines)
        
        return cls(
            title=title,
            description=description,
            branch_name=branch_name,
            dependencies=dependencies
        )
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any], branch_name: str = None) -> 'Chunk':
        """
        Create a Chunk object from a dictionary.
        
        Args:
            data: The dictionary containing chunk data
            branch_name: Optional branch name to use if not in the data
            
        Returns:
            Chunk: A new Chunk object
        """
        title = data.get("title", "Untitled Chunk")
        description = data.get("description", "")
        chunk_branch_name = data.get("branch_name", branch_name)
        dependencies = data.get("dependencies", [])
        
        return cls(
            title=title,
            description=description,
            branch_name=chunk_branch_name,
            dependencies=dependencies
        )
    
    def to_text(self) -> str:
        """
        Convert the chunk to a text representation.
        
        Returns:
            str: The text representation of the chunk
        """
        text = f"# {self.title}\n\n{self.description}"
        
        if self.dependencies:
            text += f"\n\nDependencies: {', '.join(self.dependencies)}"
        
        if self.branch_name:
            text += f"\n\nGit Branch: {self.branch_name}"
            
        return text
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the chunk to a dictionary representation.
        
        Returns:
            Dict[str, Any]: The dictionary representation of the chunk
        """
        return {
            "title": self.title,
            "description": self.description,
            "branch_name": self.branch_name,
            "dependencies": self.dependencies
        }
    
    def get_commit_message(self) -> str:
        """
        Generate a commit message for this chunk.
        
        Returns:
            str: The commit message
        """
        return f"Implement {self.title}"
    
    def get_display_content(self) -> str:
        """
        Get the content to display to the user, without title and branch name.
        
        Returns:
            str: The content to display
        """
        return self.description


class ChunkingResult:
    """
    Represents the complete result of a task chunking operation.
    """
    def __init__(self, 
                 chunks: List[Chunk], 
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
        # Extract violated tests from raw_data if available
        self.violated_tests = self.raw_data.get("list_of_violated_tests", []) if self.raw_data else []
        
    @property
    def text_chunks(self) -> List[str]:
        """
        Get the chunks as text representations for backward compatibility.
        
        Returns:
            List[str]: The chunks as text
        """
        return [chunk.to_text() for chunk in self.chunks]
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert the chunking result to a dictionary representation."""
        return {
            "branch_name": self.branch_name,
            "analysis": self.analysis,
            "strategy": self.strategy,
            "num_chunks": self.num_chunks,
            "chunks": [chunk.to_dict() for chunk in self.chunks],
            "violated_tests": self.violated_tests,
            "raw_data": self.raw_data
        }
    
    def get_chunk_titles(self) -> List[str]:
        """Extract titles from chunks."""
        return [chunk.title for chunk in self.chunks]
        
    def get_commit_messages(self) -> List[str]:
        """Generate commit messages for each chunk."""
        return [chunk.get_commit_message() for chunk in self.chunks]


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
You are a senior software engineer tasked with breaking down a complex programming task into smaller, manageable chunks. Your goal is to analyze the task instructions and determine the optimal way to split them into separate sub-tasks that can be implemented independently or in sequence. It is important that the chain of chunks is complete and that each chunk is self-contained and can be reasonably implemented.
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
5. Prioritize chunks based on dependencies (what needs to be done first), each chunk should build on the previous one!
6. Keep the number of chunks reasonable (typically 1-10 chunks, depending on complexity)
7. For simple tasks, it's perfectly acceptable to have just 1 chunk
8. For very complex tasks, don't exceed 10 chunks to maintain manageability
9. Create a single descriptive git branch name for the ENTIRE task (lowercase with hyphens, no spaces)
   - This branch name should be prefixed with 'tac/feature/' (e.g., 'tac/feature/add-user-authentication')
   - The branch name should be descriptive of the overall task, not individual chunks
10. Each chunk should include its own tests where appropriate - no separate integration test is needed
11. If there are tests that are violated by the chunking, list them in the 'list_of_violated_tests' field
</chunking_rules>
12. A single chunk should not be too big and just focus on one thing
13. Don't create chunks that only contain tests

<output_format>
Provide your analysis in the following JSON format:

```json
{{
  "strategy": "Explain briefly what you did, and why you go for this chunking strategy",
  "branch_name": "tac/feature/descriptive-git-branch-name-for-entire-task",
  "list_of_violated_tests": ["tests/test_file1.py:test_name1", "tests/test_file2.py:test_name2"],
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
                
                # Extract the chunk descriptions and create Chunk objects
                chunks = []
                for chunk_dict in chunk_data["chunks"]:
                    if "title" in chunk_dict and "description" in chunk_dict:
                        # Create a Chunk object using from_dict
                        chunk = Chunk.from_dict(chunk_dict, branch_name=branch_name)
                        chunks.append(chunk)
                
                if not chunks:
                    logger.warning("No valid chunks found, returning original as single chunk")
                    return self._create_default_result(task_instructions)
                
                # Create and return the ChunkingResult
                analysis = chunk_data.get("analysis", "Task chunked successfully")
                strategy = chunk_data.get("strategy", analysis)
                num_chunks = chunk_data.get("num_chunks", len(chunks))
                
                # Ensure raw_data contains list_of_violated_tests if present in the response
                if "list_of_violated_tests" not in chunk_data:
                    chunk_data["list_of_violated_tests"] = []
                
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
        chunk = Chunk(
            title="Complete Task Implementation",
            description=task_instructions,
            branch_name=branch_name
        )
        
        # Create and return the result
        return ChunkingResult(
            chunks=[chunk],
            branch_name=branch_name,
            analysis="Task was not chunked due to processing error or invalid response",
            strategy="Task was not chunked due to processing error or invalid response",
            num_chunks=1,
            raw_data={"error": "Failed to process task chunking", "list_of_violated_tests": []}
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