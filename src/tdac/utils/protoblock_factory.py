import json
import uuid
from dataclasses import dataclass
from typing import List, Optional
from tdac.utils.seed_generator import generate_instructions
from tdac.core.llm import LLMClient, Message

@dataclass
class ProtoBlockSpec:
    """Specification for a protoblock"""
    task_specification: str
    test_specification: str
    test_data: str
    write_files: List[str]
    context_files: List[str]
    commit_message: str
    block_id: str = None

class ProtoBlockFactory:
    """Factory class for creating protoblocks"""
    
    def __init__(self):
        self.llm_client = LLMClient()
    
    def create_from_directory(self, directory: str, template_type: str = "default") -> ProtoBlockSpec:
        """
        Create a protoblock from a directory using the specified template type.
        
        Args:
            directory: Path to the directory to analyze
            template_type: Type of template to use (default, refactor, test, error)
            
        Returns:
            ProtoBlockSpec object containing the protoblock specification
        """
        # Generate instructions for the LLM
        instructions = generate_instructions(directory, template_type)
        
        # Create messages for LLM
        messages = [
            Message(role="system", content="You are a helpful assistant that generates JSON protoblocks for code tasks. Follow the template exactly and ensure the output is valid JSON. Do not use markdown code fences in your response."),
            Message(role="user", content=instructions)
        ]
        
        # Get response from LLM
        response = self.llm_client.chat_completion(messages)
        json_content = response.choices[0].message.content.strip()
        
        # Strip markdown code fences if present
        if json_content.startswith("```"):
            lines = json_content.split("\n")
            start_idx = next((i for i, line in enumerate(lines) if line.startswith("```")), 0) + 1
            end_idx = next((i for i, line in enumerate(lines[start_idx:], start_idx) if line.startswith("```")), len(lines))
            json_content = "\n".join(lines[start_idx:end_idx]).strip()
        
        # Parse JSON content
        try:
            data = json.loads(json_content)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON response from LLM: {e}")
        
        # Create ProtoBlockSpec with UUID
        return ProtoBlockSpec(
            task_specification=data["task"]["specification"],
            test_specification=data["test"]["specification"],
            test_data=data["test"]["data"],
            write_files=data["write_files"],
            context_files=data.get("context_files", []),
            commit_message=data.get("commit_message", "TDAC: Update"),
            block_id=str(uuid.uuid4())
        )
    
    def save_protoblock(self, spec: ProtoBlockSpec, template_type: str) -> str:
        """
        Save a protoblock specification to a file.
        
        Args:
            spec: ProtoBlockSpec object containing the specification
            template_type: Type of template used
            
        Returns:
            Path to the saved protoblock file
        """
        data = {
            "task": {
                "specification": spec.task_specification
            },
            "test": {
                "specification": spec.test_specification,
                "data": spec.test_data,
                "replacements": spec.write_files
            },
            "write_files": spec.write_files,
            "context_files": spec.context_files,
            "commit_message": spec.commit_message
        }
        
        # Save to file using UUID
        filename = f".tdac_protoblock_{template_type}_{spec.block_id}.json"
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
            
        return filename 