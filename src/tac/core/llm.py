"""Module for handling LLM (Language Model) interactions."""

import os
import base64
from enum import Enum
from typing import List, Dict, Optional, Union, Any, Tuple
from dataclasses import dataclass
import logging
import requests
from PIL import Image
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
    
    def __init__(self, config_override: Optional[Dict] = None, llm_type: str = "weak"):
        """Initialize client with config from file or provided config.
        
        Args:
            config_override: Optional config override dictionary
            llm_type: Type of LLM to use ("weak", "strong", or "vision", defaults to "weak")
        """
        # Get config from centralized config
        llm_config = config.get_llm_config(llm_type)
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

    def vision_chat_completion(
        self,
        messages: List[Message],
        image_path: str,
        temperature: Optional[float] = None,
    ) -> str:
        """
        Send a vision chat completion request to the LLM with an image.
        
        Args:
            messages: List of messages in the conversation
            image_path: Path to the image file
            temperature: Controls randomness (0.0 to 1.0)
            
        Returns:
            str: The content of the model's response message
        """
        # Verify the image exists
        if not os.path.exists(image_path):
            error_msg = f"Image file not found: {image_path}"
            logger.error(error_msg)
            return f"Vision LLM failure: {error_msg}"
        
        # Process the image to ensure it's in a compatible format
        try:
            # Open and convert the image to ensure it's in a compatible format
            with Image.open(image_path) as img:
                # Create a temporary file for the processed image
                temp_dir = os.path.dirname(image_path)
                temp_filename = f"processed_{os.path.basename(image_path)}"
                processed_path = os.path.join(temp_dir, temp_filename)
                
                # Convert to RGB and save as JPEG (most compatible format)
                img_rgb = img.convert('RGB')
                img_rgb.save(processed_path, format='JPEG')
                logger.info(f"Image processed and saved to {processed_path}")
                
                # Read the processed image
                with open(processed_path, "rb") as image_file:
                    base64_image = base64.b64encode(image_file.read()).decode('utf-8')
                
                # Clean up the temporary file
                try:
                    os.remove(processed_path)
                except Exception as e:
                    logger.warning(f"Failed to remove temporary processed image: {str(e)}")
        except Exception as e:
            error_msg = f"Failed to process image: {str(e)}"
            logger.error(error_msg)
            return f"Vision LLM failure: {error_msg}"
        
        # Convert messages to the format expected by the API
        formatted_messages = []
        
        for i, msg in enumerate(messages):
            # For the last user message, add the image
            if i == len(messages) - 1 and msg.role == "user":
                formatted_messages.append({
                    "role": msg.role,
                    "content": [
                        {"type": "text", "text": msg.content},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                })
            else:
                formatted_messages.append({
                    "role": msg.role,
                    "content": msg.content
                })
        
        # Prepare completion parameters
        params = {
            "model": self.config.model,
            "messages": formatted_messages,
            "stream": False,
            "timeout": self.config.settings.timeout,
        }
        
        # Use settings from config if not overridden
        if temperature is None:
            temperature = self.config.settings.temperature
        params["temperature"] = temperature
        
        max_tokens = self.config.settings.max_tokens
        if max_tokens:
            params["max_tokens"] = max_tokens
            
        try:
            logger.debug(f"Vision LLM pre: Params: {params}")
            response = self.client.chat.completions.create(**params)
            logger.debug(f"Vision LLM post: {response}")
            if not response or not response.choices:
                raise ValueError("Empty response received from API")
            return response.choices[0].message.content
        except Exception as e:
            provider_name = self.config.provider.capitalize()
            # Add more detailed error information
            error_msg = f"{provider_name} Vision API call failed: {str(e)}"
            if hasattr(e, 'response'):
                error_msg += f"\nResponse status: {e.response.status_code}"
                try:
                    error_msg += f"\nResponse body: {e.response.text}"
                except:
                    pass
            logger.error(error_msg)
            return f"Vision LLM failure: {error_msg}"

    def analyze_screenshot(
        self,
        program_runner,
        prompt: str,
        temperature: Optional[float] = None,
    ) -> str:
        """
        Analyze a screenshot taken by a ProgramRunner using vision model.
        
        Args:
            program_runner: An instance of ProgramRunner that has taken a screenshot
            prompt: The prompt to send to the vision model
            temperature: Controls randomness (0.0 to 1.0)
            
        Returns:
            str: The content of the model's response message
        """
        # Get the screenshot path from the program runner
        screenshot_path = program_runner.get_screenshot_path()
        if not screenshot_path or not os.path.exists(screenshot_path):
            error_msg = "No screenshot available or screenshot file not found"
            logger.error(error_msg)
            return f"Vision LLM failure: {error_msg}"
        
        # Create messages for the vision model
        messages = [
            Message(role="system", content="You are a helpful assistant that can analyze images"),
            Message(role="user", content=prompt)
        ]
        
        # Send the screenshot to the vision model
        return self.vision_chat_completion(messages, screenshot_path, temperature)

# Example usage:
if __name__ == "__main__":
    # Example messages
    messages = [
        Message(role="system", content="You are a helpful assistant"),
        Message(role="user", content="Hello!")
    ]
    
    # Example with weak model (default)
    print("Using weak model:")
    client_weak = LLMClient(llm_type="weak")
    response_weak = client_weak.chat_completion(messages)
    print(response_weak)
    
    # Example with strong model
    print("\nUsing strong model:")
    client_strong = LLMClient(llm_type="strong")
    response_strong = client_strong.chat_completion(messages)
    print(response_strong)
    
    # Example with vision model
    print("\nUsing vision model:")
    image_path = os.path.expanduser("~/Downloads/tmpip7ugsgv.png")
    
    # Check if the image exists
    if os.path.exists(image_path):
        client_vision = LLMClient(llm_type="vision")
        vision_messages = [
            Message(role="system", content="You are a helpful assistant that can analyze images"),
            Message(role="user", content="Do you see a black background and a red dot in the middle?")
        ]
        print(f"Analyzing image at: {image_path}")
        response_vision = client_vision.vision_chat_completion(vision_messages, image_path)
        print(response_vision)
    else:
        print(f"Image not found at {image_path}. Vision example skipped.") 
