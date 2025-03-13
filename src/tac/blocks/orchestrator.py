import logging
import json
from typing import Dict, List, Optional, Any
from tac.core.llm import LLMClient, Message
from tac.core.config import config
from tac.core.log_config import setup_logging
from tac.utils.project_files import ProjectFiles

logger = setup_logging('tac.blocks.orchestrator')


class ProtoBlockRecipe:
    """
    Represents a single recipe for creating a ProtoBlock from a task to be implemented.
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
    def from_text(cls, text: str) -> 'ProtoBlockRecipe':
        """
        Create a ProtoBlockRecipe object from a text representation.
        
        Args:
            text: The text representation of the recipe
            
        Returns:
            ProtoBlockRecipe: A new ProtoBlockRecipe object
        """
        title = "Untitled Recipe"
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
    def from_dict(cls, data: Dict[str, Any], branch_name: str = None) -> 'ProtoBlockRecipe':
        """
        Create a ProtoBlockRecipe object from a dictionary.
        
        Args:
            data: The dictionary containing recipe data
            branch_name: Optional branch name to use if not in the data
            
        Returns:
            ProtoBlockRecipe: A new ProtoBlockRecipe object
        """
        title = data.get("title", "Untitled Recipe")
        description = data.get("description", "")
        recipe_branch_name = data.get("branch_name", branch_name)
        dependencies = data.get("dependencies", [])
        
        return cls(
            title=title,
            description=description,
            branch_name=recipe_branch_name,
            dependencies=dependencies
        )
    
    def to_text(self) -> str:
        """
        Convert the recipe to a text representation.
        
        Returns:
            str: The text representation of the recipe
        """
        text = f"# {self.title}\n\n{self.description}"
        
        if self.dependencies:
            text += f"\n\nDependencies: {', '.join(self.dependencies)}"
        
        if self.branch_name:
            text += f"\n\nGit Branch: {self.branch_name}"
            
        return text
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the recipe to a dictionary representation.
        
        Returns:
            Dict[str, Any]: The dictionary representation of the recipe
        """
        return {
            "title": self.title,
            "description": self.description,
            "branch_name": self.branch_name,
            "dependencies": self.dependencies
        }
    
    def get_commit_message(self) -> str:
        """
        Generate a commit message for this recipe.
        
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


class ProtoBlockRecipeResult:
    """
    Represents the complete result of a task chunking operation.
    """
    def __init__(self, 
                 recipes: List[ProtoBlockRecipe], 
                 branch_name: str, 
                 analysis: str = None,
                 strategy: str = None,
                 num_recipes: int = None,
                 raw_data: Dict[str, Any] = None):
        self.recipes = recipes
        self.branch_name = branch_name
        self.analysis = analysis
        self.strategy = strategy or analysis  # Use strategy if provided, otherwise fall back to analysis
        self.num_recipes = num_recipes or len(recipes)
        self.raw_data = raw_data or {}
        # Extract violated tests from raw_data if available
        self.violated_tests = self.raw_data.get("list_of_violated_tests", []) if self.raw_data else []
        
    @property
    def text_recipes(self) -> List[str]:
        """
        Get the recipes as text representations for backward compatibility.
        
        Returns:
            List[str]: The recipes as text
        """
        return [recipe.to_text() for recipe in self.recipes]
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert the chunking result to a dictionary representation."""
        return {
            "branch_name": self.branch_name,
            "analysis": self.analysis,
            "strategy": self.strategy,
            "num_recipes": self.num_recipes,
            "recipes": [recipe.to_dict() for recipe in self.recipes],
            "violated_tests": self.violated_tests,
            "raw_data": self.raw_data
        }
    
    def get_recipe_titles(self) -> List[str]:
        """Extract titles from recipes."""
        return [recipe.title for recipe in self.recipes]
        
    def get_commit_messages(self) -> List[str]:
        """Generate commit messages for each recipe."""
        return [recipe.get_commit_message() for recipe in self.recipes]

    # For backward compatibility
    @property
    def chunks(self):
        return self.recipes
    
    @property
    def text_chunks(self):
        return self.text_recipes
    
    @property
    def num_chunks(self):
        return self.num_recipes
    
    def get_chunk_titles(self):
        return self.get_recipe_titles()


class MultiBlockOrchestrator:
    """
    Uses an LLM to intelligently split task instructions into appropriate chunks (blocks)
    based on complexity, dependencies, and logical separation, then manages the execution
    of each block in the correct order.
    """
    
    def __init__(self):
        logger.info("Initializing MultiBlockOrchestrator")
        self.llm_client = LLMClient(llm_type="strong")
    
    def execute(self, task_instructions: str, codebase: str, args=None, voice_ui=None, git_manager=None):
        """
        Executes a task by chunking it and then processing each chunk sequentially.
        
        Args:
            task_instructions: The full task instructions to be executed
            codebase: A summary of the codebase for context
            args: Command line arguments (optional)
            voice_ui: Voice UI instance (optional)
            git_manager: Git manager instance (optional)
            
        Returns:
            bool: True if execution was successful, False otherwise
        """
        import sys
        from tac.blocks.processor import BlockProcessor
        
        if voice_ui is not None:
            raise NotImplementedError("Voice UI is not supported with orchestrator")
            
        # Chunk the task instructions
        logger.info("Using orchestrator to chunk instructions into multiple protoblocks")
        recipe_result = self.chunk(task_instructions, codebase)
        
        # Get the recipes from the result
        recipes = recipe_result.recipes
        
        logger.info(f"Instructions chunked into {len(recipes)} potential protoblocks (recipes)")
        
        # Get branch name directly from the result
        branch_name = recipe_result.branch_name
        
        # Get commit messages for each recipe
        commit_messages = recipe_result.get_commit_messages()
        
        # Display the chunked tasks with commit messages
        logger.info("🔍 Task Analysis Complete")
        if recipe_result.strategy:
            logger.info(f"Strategy: {recipe_result.strategy}")
        logger.info(f"The task has been divided into {len(recipes)} parts that will be executed one by one", heading=True)
        if branch_name:
            logger.info(f"🌿 Git Branch: {branch_name}")
        
        # Display violated tests if any
        if hasattr(recipe_result, 'violated_tests') and recipe_result.violated_tests:
            logger.warning("⚠️ Tests that may be violated by this chunking:")
            for test in recipe_result.violated_tests:
                logger.warning(f"  - {test}")
        else:
            logger.info("✅ No tests will be violated by this chunking")
        
        # Display recipes with 1-based indexing for user-friendly output
        for i, recipe in enumerate(recipes):
            # Display recipe with commit message but without branch name
            logger.info(f"Showing Protoblock recipe {i+1}/{len(recipes)} ---")
            # Display the recipe content without title and branch name
            logger.info(recipe.get_display_content())
            logger.info(f"📝 Commit: {commit_messages[i]}")
        
        # Ask user if they want to proceed with execution only if confirm_multiblock_execution is enabled
        if config.general.confirm_multiblock_execution:
            logger.info("Confirmation required before execution")
            proceed = input("Do you want to proceed with execution? (y/n): ").lower().strip()
            
            if proceed != 'y':
                logger.info("Execution cancelled by user")
                return False
        else:
            logger.info("Proceeding with execution automatically")
            print("\nProceeding with execution automatically.")
        
        logger.info(f"Using branch name: {branch_name}")
        
        # Switch to branch if git is enabled and branch name is available
        original_branch = None
        if config.git.enabled and branch_name and git_manager:
            original_branch = git_manager.get_current_branch()
            logger.info(f"Switching from branch '{original_branch}' to '{branch_name}'")
            logger.info(f"🔄 Switching to branch: {branch_name}")
            if not git_manager.checkout_branch(branch_name, create=True):
                logger.warning(f"Failed to switch to branch {branch_name}, continuing in current branch")
        
        # Execute each recipe sequentially with 0-based indexing
        success = True
        
        # Disable auto-push for orchestrator mode
        if config.git.enabled:
            config.override_with_dict({'git': {'auto_push_if_success': False}})
            logger.info("Auto-push disabled for orchestrator mode (commits will be created but not pushed)")
        
        project_files = ProjectFiles()
        
        for i, recipe in enumerate(recipes):
            logger.info(f"🚀 Executing Protoblock Recipe {i+1}/{len(recipes)}...", heading=True)

            # Update codebase if it's not the first recipe
            if i > 0:
                project_files.update_summaries()
                codebase = project_files.get_codebase_summary()
            
            # Convert the recipe to text for the BlockProcessor
            recipe_text = recipe.to_text()
            
            # Execute the recipe
            protoblock = None
            if args and hasattr(args, 'json') and args.json:
                from tac.blocks.model import ProtoBlock
                protoblock = ProtoBlock.load(args.json)
                logger.info(f"📄 Loaded protoblock from: {args.json}")
            
            block_processor = BlockProcessor(recipe_text, codebase, protoblock=protoblock)
            recipe_success = block_processor.run_loop()
            
            if not recipe_success:
                logger.error(f"❌ Protoblock {i+1}/{len(recipes)} execution failed.")
                success = False
                break
            else:
                logger.info(f"✅ Protoblock {i+1}/{len(recipes)} completed successfully!")
                
                # Create a commit for this recipe if git is enabled
                if config.git.enabled and git_manager:
                    commit_message = commit_messages[i]
                    logger.info(f"📝 Creating commit: {commit_message}")
                    git_manager.commit(commit_message)
        
        # Don't switch back to original branch - stay on feature branch
        # if config.git.enabled and original_branch and git_manager:
        #     print(f"\n🔄 Switching back to branch: {original_branch}")
        #     git_manager.checkout_branch(original_branch)
        
        if success:
            logger.info("✅ Task completed successfully!", heading=True)
            logger.info("Each recipe included its own tests, so no additional integration tests are needed.")
            
            # Add instructions for pushing changes if git is enabled
            if config.git.enabled and branch_name and git_manager:
                logger.info(f"📝 Git status:")
                logger.info(f"- All changes have been committed to branch '{branch_name}'")
                logger.info(f"- You are now on the feature branch '{branch_name}' with all changes")
                logger.info(f"- To push changes manually, run: git push origin {branch_name}")
                if original_branch:
                    logger.info(f"- To switch back to your original branch, run: git checkout {original_branch}")
            
            logger.info("Task completed successfully with per-recipe tests.")
        else:
            logger.error("❌ Task execution failed.", heading=True)
            return False
            
        return success
    
    def chunk(self, task_instructions: str, codebase: str) -> ProtoBlockRecipeResult:
        """
        Analyzes the task instructions and splits them into appropriate chunks.
        
        Args:
            task_instructions: The full task instructions to be split
            codebase: A summary of the codebase for context
            
        Returns:
            ProtoBlockRecipeResult: A structured result containing all recipes and metadata
        """
        logger.info("Starting LLM-based chunking of the task instructions into protoblocks")
        logger.debug(f"Task instructions length: {len(task_instructions)}")
        
        try:
            # Prepare prompt
            chunking_prompt = f"""<purpose>
You are a senior software engineer tasked with breaking down a complex programming task into smaller, manageable chunks. Your goal is to analyze the task instructions and determine the optimal way to split them into separate sub-tasks that can be implemented independently or in sequence. It is important that the chain of chunks is complete and that each chunk is self-contained and can be reasonably implemented. The end goal needs to bring everything together and the task needs to be completed. Your goal is to think everything through end to end and focusing on the big picture of the deliverable.
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
1. Analyze the complexity and scope of the task and 
2. identify logical boundaries where the task can be split, considering dependencies between different parts of the task
3. Ensure each chunk is self-contained and can be reasonably implemented
4. Prioritize chunks based on dependencies (what needs to be done first), each chunk should build on the previous one!
5. For simple tasks, it's perfectly acceptable to have just 1 chunk, for very complex tasks, don't exceed 10 chunks to maintain manageability
6. Each chunk should include its own tests where appropriate - no separate integration test is needed, and don't create chunks that only contain tests
7. mention the files that we are creating on the way and where they should be placed, e.g. src/tac/blocks/orchestrator.py and use them throughout the task
8. Create a single descriptive git branch name for the ENTIRE task (lowercase with hyphens, no spaces)
   - This branch name should be prefixed with 'tac/feature/' (e.g., 'tac/feature/add-user-authentication')
   - The branch name should be descriptive of the overall task, not individual chunks
9. If there are tests that are violated by the chunking, list them in the 'list_of_violated_tests' field
</chunking_rules>

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
            
            logger.debug("Task chunking starting, sending request to LLM")
            response = self.llm_client.chat_completion(messages)
            
            if not response or not response.strip():
                logger.error("Received empty response from LLM")
                return self._create_default_result(task_instructions)
            
            logger.debug("Successfully received LLM response")

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
                
                logger.info(f"Using branch name for all protoblock recipes: {branch_name}")
                
                # Extract the chunk descriptions and create ProtoBlockRecipe objects
                recipes = []
                for chunk_dict in chunk_data["chunks"]:
                    if "title" in chunk_dict and "description" in chunk_dict:
                        # Create a ProtoBlockRecipe object using from_dict
                        recipe = ProtoBlockRecipe.from_dict(chunk_dict, branch_name=branch_name)
                        recipes.append(recipe)
                
                if not recipes:
                    logger.warning("No valid recipes found, returning original as single recipe")
                    return self._create_default_result(task_instructions)
                
                # Create and return the ProtoBlockRecipeResult
                analysis = chunk_data.get("analysis", "Task chunked successfully")
                strategy = chunk_data.get("strategy", analysis)
                num_recipes = chunk_data.get("num_chunks", len(recipes))
                
                # Ensure raw_data contains list_of_violated_tests if present in the response
                if "list_of_violated_tests" not in chunk_data:
                    chunk_data["list_of_violated_tests"] = []
                
                result = ProtoBlockRecipeResult(
                    recipes=recipes,
                    branch_name=branch_name,
                    analysis=analysis,
                    strategy=strategy,
                    num_recipes=num_recipes,
                    raw_data=chunk_data
                )
                    
                logger.info(f"Successfully chunked task into {len(recipes)} protoblocks")
                return result
                
            except json.JSONDecodeError as e:
                logger.error(f"Error decoding JSON from LLM response: {str(e)}")
                return self._create_default_result(task_instructions)
                
        except Exception as e:
            logger.error(f"Error during task chunking: {str(e)}", exc_info=True)
            return self._create_default_result(task_instructions)
    
    def _create_default_result(self, task_instructions: str) -> ProtoBlockRecipeResult:
        """
        Creates a default ProtoBlockRecipeResult with a single recipe containing the original task.
        
        Args:
            task_instructions: The original task instructions
            
        Returns:
            ProtoBlockRecipeResult: A default chunking result with one recipe
        """
        # Create a default branch name
        words = task_instructions.split()[:5]
        feature_name = "-".join([w.lower() for w in words if w.isalnum()])
        if not feature_name:
            feature_name = "task-implementation"
        branch_name = f"tac/feature/{feature_name}"
        
        # Create a single recipe with the original task
        recipe = ProtoBlockRecipe(
            title="Complete Task Implementation",
            description=task_instructions,
            branch_name=branch_name
        )
        
        # Create and return the result
        return ProtoBlockRecipeResult(
            recipes=[recipe],
            branch_name=branch_name,
            analysis="Task was not chunked due to processing error or invalid response",
            strategy="Task was not chunked due to processing error or invalid response",
            num_recipes=1,
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