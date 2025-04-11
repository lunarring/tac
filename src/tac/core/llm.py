"""Module for handling LLM (Language Model) interactions."""

import os
import base64
from enum import Enum
from typing import List, Dict, Optional, Union, Any, Tuple
from dataclasses import dataclass
import logging
import requests
from PIL import Image
from io import BytesIO
from openai import OpenAI
from openai.types.chat import ChatCompletion
from tac.core.log_config import setup_logging
from tac.core.config import config

logger = setup_logging('tac.core.llm')

class LLMProvider(Enum):
    """Supported LLM providers."""
    DEEPSEEK = "deepseek"
    OPENAI = "openai"
    GEMINI = "gemini"

@dataclass
class Message:
    """Represents a chat message."""
    role: str
    content: str

class LLMClient:
    """Client for interacting with Language Models."""
    
    def __init__(self, component: str = None, llm_type: str = "weak", config_override: Optional[Dict] = None):
        """Initialize client with config from file or provided config.
        
        Args:
            component: Component identifier to determine which LLM template to use
            llm_type: Legacy parameter - type of LLM to use ("weak", "strong", or "vision")
            config_override: Optional config override dictionary
        """
        # Get config from centralized config
        llm_config = config.get_llm_config(llm_type, component)
        if config_override:
            # Override settings if provided
            for key, value in config_override.items():
                setattr(llm_config, key, value)
        
        self.config = llm_config
        self.client = self._initialize_client()
    
    def _initialize_client(self) -> Union[OpenAI, Any]:
        """Initialize the client with appropriate configuration."""
        # Handle Gemini client initialization
        if self.config.provider == LLMProvider.GEMINI.value:
            try:
                import google.generativeai as genai
                api_key = self.config.api_key or os.getenv("GEMINI_API_KEY")
                if not api_key:
                    raise ValueError("Gemini API key is required. Set it in the config or as GEMINI_API_KEY environment variable.")
                genai.configure(api_key=api_key)
                return genai
            except ImportError:
                logger.error("To use Gemini, please install the google-generativeai package: pip install google-generativeai")
                raise
        
        # Handle OpenAI client initialization (default)
        kwargs = {
            "api_key": self.config.api_key or os.getenv(f"{self.config.provider.upper()}_API_KEY"),
            "timeout": self.config.settings.timeout,
        }
        if self.config.base_url:
            kwargs["base_url"] = self.config.base_url
        elif self.config.provider == "deepseek":
            kwargs["base_url"] = "https://api.deepseek.com"
            
        return OpenAI(**kwargs)
    
    def _inject_reasoning_into_system(self, messages: List[Message]) -> List[Message]:
        """
        For reasoning models, incorporate the reasoning strength into the system prompt messages.
        For non-reasoning (e.g., vision model 'gpt-4o'), do nothing.
        """
        # Skip for Gemini or vision models
        if self.config.provider == LLMProvider.GEMINI.value or self.config.model == "gpt-4o":
            return messages
        
        for msg in messages:
            if msg.role == "system":
                msg.content = f"{msg.content}\n(Reasoning Effort: {self.config.settings.reasoning_effort})"
        return messages

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
        # Lightweight chat functionality for weak LLM: simply append all incoming message contents.
        if self.config.model.lower() == "weak":
            combined_response = " ".join(message.content for message in messages)
            return combined_response
        
        # Handle Gemini API
        if self.config.provider == LLMProvider.GEMINI.value:
            return self._gemini_chat_completion(messages, temperature, max_tokens, stream)
        
        # Inject reasoning effort into system prompts for reasoning models.
        messages = self._inject_reasoning_into_system(messages)
        
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
        
        # Prepare completion parameters without passing 'reasoning_effort'
        params = {
            "model": self.config.model,
            "messages": formatted_messages,
            "stream": stream,
            "timeout": self.config.settings.timeout,
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
            # Log a summary of the response instead of the full object
            logger.debug(f"LLM post: Response received: {response}")
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
    
    def _gemini_chat_completion(
        self,
        messages: List[Message],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False,
    ) -> str:
        """
        Send a chat completion request to the Gemini API.
        
        Args:
            messages: List of messages in the conversation
            temperature: Controls randomness (0.0 to 1.0)
            max_tokens: Maximum number of tokens to generate
            stream: Whether to stream the response
            
        Returns:
            str: The content of the model's response message
        """
        try:
            # Convert to Gemini message format
            gemini_messages = []
            
            # Gemini uses "user" and "model" roles instead of "user" and "assistant"
            role_mapping = {
                "user": "user",
                "assistant": "model",
                "system": "user"  # Gemini doesn't have system messages, prepend to first user message
            }
            
            system_content = ""
            for msg in messages:
                if msg.role == "system":
                    system_content += msg.content + "\n"
                else:
                    gemini_role = role_mapping.get(msg.role, "user")
                    content = msg.content
                    
                    # If this is the first user message and we have system content, prepend it
                    if gemini_role == "user" and system_content and not any(m.get("role") == "user" for m in gemini_messages):
                        content = system_content + "\n" + content
                        system_content = ""  # Clear after using
                    
                    gemini_messages.append({"role": gemini_role, "parts": [{"text": content}]})
            
            # If we have system content but no user messages to attach it to, add it as a user message
            if system_content:
                gemini_messages.append({"role": "user", "parts": [{"text": system_content}]})
                # Add a model response to maintain the conversation flow
                gemini_messages.append({"role": "model", "parts": [{"text": "I understand."}]})
            
            # Configure generation parameters
            generation_config = {}
            
            if temperature is None:
                temperature = self.config.settings.temperature
            generation_config["temperature"] = temperature
            
            if max_tokens is None:
                max_tokens = self.config.settings.max_tokens
            if max_tokens:
                generation_config["max_output_tokens"] = max_tokens
            
            # Get the model
            model = self.client.GenerativeModel(self.config.model)
            
            # Create the chat session
            chat = model.start_chat(history=gemini_messages[:-1] if gemini_messages else [])
            
            # Generate the response
            logger.debug(f"Gemini pre: Messages: {gemini_messages}, Config: {generation_config}")
            response = chat.send_message(
                gemini_messages[-1]["parts"][0]["text"] if gemini_messages else "",
                generation_config=generation_config,
                stream=stream
            )
            logger.debug(f"Gemini post: Response received")
            
            if stream:
                # Collect streamed response
                full_response = ""
                for chunk in response:
                    if chunk.text:
                        full_response += chunk.text
                return full_response
            else:
                return response.text
                
        except Exception as e:
            error_msg = f"Gemini API call failed: {str(e)}"
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
        
        # Handle Gemini vision
        if self.config.provider == LLMProvider.GEMINI.value:
            return self._gemini_vision_chat_completion(messages, image_path, temperature)
            
        # Prepare the image for the API call
        try:
            # Open and potentially resize the image
            with Image.open(image_path) as img:
                # Ensure image is in a supported format
                if img.format not in ['JPEG', 'PNG', 'GIF', 'WEBP']:
                    logger.warning(f"Converting image from {img.format} to PNG")
                    img = img.convert('RGB')
                    temp_path = f"{os.path.splitext(image_path)[0]}_converted.png"
                    img.save(temp_path, format='PNG')
                    image_path = temp_path
                
                # Check if we need to resize the image
                max_dim = self.config.settings.max_image_dimension
                if max(img.width, img.height) > max_dim:
                    logger.info(f"Resizing image to fit within {max_dim}x{max_dim}")
                    img = self.downscale_image(img, max_dim, max_dim)
                    temp_path = f"{os.path.splitext(image_path)[0]}_resized.png"
                    img.save(temp_path, format='PNG')
                    image_path = temp_path
        except Exception as e:
            error_msg = f"Error processing image: {str(e)}"
            logger.error(error_msg)
            return f"Vision LLM failure: {error_msg}"
        
        # Encode the image to base64
        try:
            with open(image_path, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode('utf-8')
        except Exception as e:
            error_msg = f"Error encoding image: {str(e)}"
            logger.error(error_msg)
            return f"Vision LLM failure: {error_msg}"
            
        # Prepare the messages
        formatted_messages = []
        for msg in messages:
            if msg.role == "user" and msg is messages[-1]:
                # For the last user message, include the image
                formatted_messages.append({
                    "role": "user",
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
        
        # Prepare API parameters
        if temperature is None:
            temperature = self.config.settings.temperature
            
        params = {
            "model": self.config.model,
            "messages": formatted_messages,
            "temperature": temperature,
        }
        
        max_tokens = self.config.settings.max_tokens
        if max_tokens:
            params["max_tokens"] = max_tokens
            
        # Make the API call
        try:
            # Create a version of params suitable for logging (without the full image data)
            log_params = params.copy()
            for msg in log_params["messages"]:
                if isinstance(msg["content"], list):
                    for content_item in msg["content"]:
                        if content_item.get("type") == "image_url":
                            content_item["image_url"]["url"] = "[BASE64_IMAGE_DATA]"
            
            logger.debug(f"Vision LLM pre: Params: {log_params}")
            response = self.client.chat.completions.create(**params)
            logger.debug(f"Vision LLM post: Response received: {response}")
            
            if not response or not response.choices:
                raise ValueError("Empty response received from API")
                
            return response.choices[0].message.content
        except Exception as e:
            provider_name = self.config.provider.capitalize()
            error_msg = f"{provider_name} vision API call failed: {str(e)}"
            logger.error(error_msg)
            return f"Vision LLM failure: {error_msg}"
    
    def _gemini_vision_chat_completion(
        self,
        messages: List[Message],
        image_path: str,
        temperature: Optional[float] = None,
    ) -> str:
        """
        Send a vision chat completion request to the Gemini API with an image.
        
        Args:
            messages: List of messages in the conversation
            image_path: Path to the image file
            temperature: Controls randomness (0.0 to 1.0)
            
        Returns:
            str: The content of the model's response message
        """
        try:
            # Process system messages
            system_content = ""
            for msg in messages:
                if msg.role == "system":
                    system_content += msg.content + "\n"
            
            # Get the last user message
            user_message = ""
            for msg in reversed(messages):
                if msg.role == "user":
                    user_message = msg.content
                    break
            
            # Prepend system content if available
            if system_content:
                user_message = system_content + "\n" + user_message
            
            # Configure generation parameters
            generation_config = {}
            
            if temperature is None:
                temperature = self.config.settings.temperature
            generation_config["temperature"] = temperature
            
            max_tokens = self.config.settings.max_tokens
            if max_tokens:
                generation_config["max_output_tokens"] = max_tokens
            
            # Load the image
            img = Image.open(image_path)
            
            # Prepare content parts with text and image
            contents = [
                {"text": user_message},
                {"image": img}
            ]
            
            # Get the model
            model = self.client.GenerativeModel(self.config.model)
            
            # Generate the response
            logger.debug(f"Gemini Vision pre: Text: {user_message}, Config: {generation_config}")
            response = model.generate_content(
                contents,
                generation_config=generation_config
            )
            logger.debug(f"Gemini Vision post: Response received")
            
            return response.text
                
        except Exception as e:
            error_msg = f"Gemini Vision API call failed: {str(e)}"
            logger.error(error_msg)
            return f"Vision LLM failure: {error_msg}"
        
    def downscale_image(self, image: Image, target_width: int, target_height: int) -> Image:
        """
        Downscale an image to fit within target dimensions while preserving aspect ratio.
        
        Args:
            image: PIL Image object
            target_width: Maximum width
            target_height: Maximum height
            
        Returns:
            PIL Image: Resized image
        """
        original_width, original_height = image.size
        
        # Calculate the scaling factor
        width_ratio = target_width / original_width
        height_ratio = target_height / original_height
        ratio = min(width_ratio, height_ratio)
        
        # Only downscale, never upscale
        if ratio >= 1:
            return image
            
        # Calculate new dimensions
        new_width = int(original_width * ratio)
        new_height = int(original_height * ratio)
        
        # Resize the image
        return image.resize((new_width, new_height), Image.LANCZOS)


# Simple test/example code
if __name__ == "__main__":
    # Example usage with component-based configuration
    client_default = LLMClient(component="chat")
    default_response = client_default.chat_completion([
        Message(role="user", content="What is the capital of France?")
    ])
    print(f"Default response: {default_response}")
    
    # Example usage with specific template (component-based)
    client_component = LLMClient(component="native_agent")  # Will use o3-mini
    component_response = client_component.chat_completion([
        Message(role="system", content="You are a helpful assistant."),
        Message(role="user", content="What are three interesting Python features?")
    ])
    print(f"\nComponent-based template (native_agent) response:")
    print(component_response)
    
    # Example usage with Gemini model (component-based)
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    if gemini_api_key:
        print("\nGemini API key found, running Gemini example...")
        try:
            # Component-based approach - using the "gemini" component
            client_gemini = LLMClient(component="gemini")
            
            gemini_response = client_gemini.chat_completion([
                Message(role="system", content="You are a helpful assistant who provides concise answers."),
                Message(role="user", content="What are three key benefits of AI in healthcare?")
            ])
            
            print("\nResponse from Gemini (component='gemini'):")
            print("-" * 50)
            print(gemini_response)
            print("-" * 50)
            
            # List available Gemini models (if needed)
            import google.generativeai as genai
            genai.configure(api_key=gemini_api_key)
            models = genai.list_models()
            available_models = [model.name for model in models if "generateContent" in model.supported_generation_methods]
            print(f"Available Gemini models: {available_models}")
            
            # Try to find Gemini 2.5 Pro if available
            gemini_25_pro = [m for m in available_models if "gemini-2.5-pro" in m]
            if gemini_25_pro:
                model_name = gemini_25_pro[0]
                print(f"\nFound Gemini 2.5 Pro! Using model: {model_name}")
                
                # Demonstrate direct override approach
                client_gemini_25 = LLMClient(config_override={
                    "provider": "gemini",
                    "model": model_name,
                    "api_key": gemini_api_key
                })
                
                gemini_25_response = client_gemini_25.chat_completion([
                    Message(role="system", content="You are a helpful assistant who provides concise answers."),
                    Message(role="user", content="Explain three key concepts of quantum computing.")
                ])
                
                print("\nResponse from Gemini 2.5 Pro (direct override):")
                print("-" * 50)
                print(gemini_25_response)
                print("-" * 50)
            
            # Example with Gemini Vision (if available)
            image_path = os.path.expanduser("~/Downloads/example.jpg")
            if os.path.exists(image_path):
                print(f"\nFound image at {image_path}, testing Gemini Vision...")
                
                client_gemini_vision = LLMClient(component="gemini_vision")
                
                vision_response = client_gemini_vision.vision_chat_completion([
                    Message(role="system", content="Describe what you see in this image in detail."),
                    Message(role="user", content="What's in this image?")
                ], image_path)
                
                print("\nGemini Vision response:")
                print("-" * 50)
                print(vision_response)
                print("-" * 50)
        except Exception as e:
            print(f"\nError running Gemini example: {str(e)}")
            print("If this is an ImportError, make sure to install the required package:")
            print("pip install google-generativeai>=0.3.1")
    else:
        print("\nGemini example skipped: GEMINI_API_KEY environment variable not set")
        print("To run the Gemini example, set your API key with:")
        print("export GEMINI_API_KEY='your-api-key-here'")
        
    print("\nSummary of component-to-model mappings:")
    print("-" * 50)
    for component, template in config._config.component_llm_mappings.items():
        model = config._config.llm_templates.get(template)
        if model:
            provider = model.provider
            model_name = model.model
            print(f"{component:20} -> {template:20} -> {provider}/{model_name}") 