"""Module for handling LLM (Language Model) interactions."""

import os
from enum import Enum
from typing import List, Dict, Optional, Union
from dataclasses import dataclass
import logging
from openai import OpenAI
from openai.types.chat import ChatCompletion
from tac.core.log_config import setup_logging
from tac.core.config import config

logger = setup_logging('tac.core.llm')

class LLMProvider(Enum):
    """Supported LLM providers."""
    DEEPSEEK = "deepseek"
    OPENAI = "openai"

@dataclass
class Message:
    """Represents a chat message."""
    role: str
    content: str

class LLMClient:
    """Client for interacting with Language Models."""
    
    def __init__(self, config_override: Optional[Dict] = None, strength: str = "weak"):
        """Initialize client with config from file or provided config.
        
        Args:
            config_override: Optional config override dictionary
            strength: Whether to use strong or weak LLM ("strong" or "weak", defaults to "weak")
        """
        # Get config from centralized config
        llm_config = config.get_llm_config(strength)
        if config_override:
            # Override settings if provided
            for key, value in config_override.items():
                setattr(llm_config, key, value)
        
        self.config = llm_config
        self.client = self._initialize_client()
    
    def _initialize_client(self) -> OpenAI:
        """Initialize the OpenAI client with appropriate configuration."""
        kwargs = {
            "api_key": self.config.api_key or os.getenv(f"{self.config.provider.upper()}_API_KEY"),
            "timeout": self.config.settings.timeout,
        }
        if self.config.base_url:
            kwargs["base_url"] = self.config.base_url
        elif self.config.provider == "deepseek":
            kwargs["base_url"] = "https://api.deepseek.com"
            
        return OpenAI(**kwargs)
    
    def chat_completion(
        self,
        messages: List[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False,
    ) -> str:
        """
        Send a chat completion request to the LLM.
        
        Args:
            messages: List of messages in the conversation
            temperature: Controls randomness (0.0 to 1.0)
            max_tokens: Maximum number of tokens to generate
            stream: Whether to stream the response
            
        Returns:
            str: The content of the model's response message
        """
        # Convert messages to the format expected by the API
        formatted_messages = []
        
        # Special handling for models that don't support system messages
        if self.config.model in ["o1-mini", "deepseek-reasoner", "o3-mini"]:
            for msg in messages:
                if msg.role == "system":
                    # Convert system message to user message
                    formatted_messages.append({
                        "role": "user",
                        "content": msg.content
                    })                    
                    formatted_messages.append({
                        "role": "assistant",
                        "content": "Understood."
                    })
                else:
                    formatted_messages.append({
                        "role": msg.role,
                        "content": msg.content
                    })
        else:
            formatted_messages = [
                {"role": msg.role, "content": msg.content}
                for msg in messages
            ]
        
        # Prepare completion parameters
        params = {
            "model": self.config.model,
            "messages": formatted_messages,
            "stream": stream,
            "timeout": self.config.settings.timeout,
            "reasoning_effort": config.general.reasoning_effort,
        }
        
        # Models that don't support temperature parameter
        if self.config.model not in ["o1-mini", "deepseek-reasoner", "o3-mini"]:
            # Use settings from config if not overridden
            if temperature is None:
                temperature = self.config.settings.temperature
            params["temperature"] = temperature
        
        if max_tokens is None:
            max_tokens = self.config.settings.max_tokens
        if max_tokens:
            params["max_tokens"] = max_tokens
            
        try:
            logger.debug(f"LLM pre: Params: {params}")
            response = self.client.chat.completions.create(**params)
            logger.debug(f"LLM post: {response}")
            if not response or not response.choices:
                raise ValueError("Empty response received from API")
            return response.choices[0].message.content
        except Exception as e:
            provider_name = self.config.provider.capitalize()
            # Add more detailed error information
            error_msg = f"{provider_name} API call failed: {str(e)}"
            if hasattr(e, 'response'):
                error_msg += f"\nResponse status: {e.response.status_code}"
                try:
                    error_msg += f"\nResponse body: {e.response.text}"
                except:
                    pass
            logger.error(error_msg)
            return f"LLM failure: {error_msg}"
        
    def _clean_code_fences(self, content: str) -> str:
        """
        Clean markdown code fences and comments from content.
        Handles JSON content more intelligently.
        
        Args:
            content: The content to clean
            
        Returns:
            str: Cleaned content ready for JSON parsing
        """
        if not content or not content.strip():
            return ""
            
        # First clean any markdown code fences
        lines = content.strip().split('\n')
        if content.strip().startswith("```"):
            # Find the content between the code fences
            start_idx = 1  # Skip the opening fence
            end_idx = len(lines)
            
            for i in range(len(lines) - 1, 0, -1):
                if lines[i].strip() == "```":
                    end_idx = i
                    break
                    
            lines = lines[start_idx:end_idx]
        
        # Now clean the lines
        cleaned_lines = []
        in_string = False
        string_char = None
        
        for line in lines:
            cleaned_line = []
            i = 0
            while i < len(line):
                char = line[i]
                
                # Handle string literals
                if char in ['"', "'"] and (i == 0 or line[i-1] != '\\'):
                    if not in_string:
                        in_string = True
                        string_char = char
                    elif char == string_char:
                        in_string = False
                        string_char = None
                
                # Handle comments only if we're not in a string
                elif char == '/' and i + 1 < len(line) and line[i + 1] == '/' and not in_string:
                    break
                
                cleaned_line.append(char)
                i += 1
            
            # Only add non-empty lines
            cleaned = ''.join(cleaned_line).strip()
            if cleaned:
                cleaned_lines.append(cleaned)
        
        return '\n'.join(cleaned_lines)

# Example usage:
if __name__ == "__main__":
    # Example messages
    messages = [
        Message(role="system", content="You are a helpful assistant"),
        Message(role="user", content="Hello!")
    ]
    
    # Create client with default config
    client = LLMClient()
    
    # Get completion
    response = client.chat_completion(messages)
    print(response)  # Now directly prints the message content 
