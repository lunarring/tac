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
    
    def __init__(self, component: str = None, llm_type: str = None, config_override: Optional[Dict] = None, model: str = None):
        """Initialize client with config from file or provided config.
        
        Args:
            component: Component identifier to determine which LLM template to use
            llm_type: Legacy parameter - type of LLM to use ("weak", "strong", or "vision")
            config_override: Optional config override dictionary
            model: Direct model name to use, bypassing component and llm_type lookup
        """
        # Add detailed logging for debugging
        logger.debug(f"Initializing LLMClient: component={component}, llm_type={llm_type}, model={model}")
        
        # If model is directly provided, use it to create a config
        if model:
            logger.info(f"Using directly provided model: {model}")
            llm_config = config.get_llm_config(component="default")
            llm_config.model = model
        else:
            # Get config from centralized config - prioritize component over llm_type if both are provided
            if component is not None:
                llm_config = config.get_llm_config(component=component)
                logger.debug(f"Using component={component} mapping: {llm_config.provider}/{llm_config.model}")
            elif llm_type is not None:
                # This is for backward compatibility
                logger.warning(f"Using deprecated llm_type='{llm_type}'. Please use component parameter instead.")
                llm_config = config.get_llm_config(llm_type=llm_type)
                logger.debug(f"Using llm_type={llm_type} mapping: {llm_config.provider}/{llm_config.model}")
            else:
                # Use default component if neither component nor llm_type is provided
                llm_config = config.get_llm_config(component="default")
                logger.debug(f"Using default component mapping: {llm_config.provider}/{llm_config.model}")
            
        if config_override:
            # Override settings if provided
            for key, value in config_override.items():
                setattr(llm_config, key, value)
                logger.debug(f"Override setting {key}={value}")
        
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
                
                # Preserve the originally requested model for reference
                original_model = self.config.model
                
                # Get available models
                try:
                    models = genai.list_models()
                    available_models = [model.name for model in models if "generateContent" in model.supported_generation_methods]
                    logger.debug(f"Available models: {available_models}")
                    
                    # Check if we want gemini-2.5-pro
                    if original_model == "gemini-2.5-pro" or "2.5-pro" in original_model:
                        # Look for the best available model in priority order
                        preferred_models = [
                            # Try to find 2.5 models first - experimental has free quota, preview doesn't
                            "models/gemini-2.5-pro-exp-03-25",  # This one has free quota
                            "models/gemini-2.5.pro-exp-03-25",  # Alternative spelling (with dot instead of dash)
                            # Only use preview if nothing else is available
                            "models/gemini-2.5-pro-preview-03-25",
                            # Then try other powerful models
                            "models/gemini-1.5-pro-latest",
                            "models/gemini-1.5-pro",
                            "models/gemini-1.5-pro-002",
                            "models/gemini-1.5-pro-001"
                        ]
                        
                        # Find the first matching model that's available
                        for preferred in preferred_models:
                            if preferred in available_models:
                                self.config.model = preferred
                                logger.info(f"Using available model {preferred} instead of requested {original_model}")
                                break
                        else:
                            # If none of the preferred models are available, use any pro model
                            pro_models = [m for m in available_models if "pro" in m]
                            if pro_models:
                                self.config.model = pro_models[0]
                                logger.info(f"Using {self.config.model} instead of requested {original_model}")
                            elif available_models:
                                # Last resort: use any available model
                                self.config.model = available_models[0]
                                logger.info(f"No Pro models available. Using {self.config.model}")
                            else:
                                logger.error("No Gemini models available")
                    else:
                        # For other models, handle normally with models/ prefix
                        if not original_model.startswith("models/") and original_model.startswith("gemini-"):
                            model_with_prefix = f"models/{original_model}"
                            if model_with_prefix in available_models:
                                self.config.model = model_with_prefix
                                logger.info(f"Using model with full path: {self.config.model}")
                            else:
                                # Try to find a similar model
                                similar_models = [m for m in available_models if original_model in m]
                                if similar_models:
                                    self.config.model = similar_models[0]
                                    logger.info(f"Using similar model: {self.config.model}")
                                elif available_models:
                                    self.config.model = available_models[0]
                                    logger.info(f"Model {original_model} not found. Using {self.config.model}")
                        elif original_model in available_models:
                            # Model name already includes prefix and exists
                            logger.info(f"Using specified model: {original_model}")
                        else:
                            # Model not found, try to find a suitable replacement
                            logger.warning(f"Model {original_model} not found in available models")
                            if available_models:
                                self.config.model = available_models[0]
                                logger.info(f"Using {self.config.model} instead")
                
                except Exception as e:
                    logger.warning(f"Error listing models: {str(e)}")
                    # Make a best guess if model listing fails
                    if original_model.startswith("gemini-2.5"):
                        self.config.model = "models/gemini-1.5-pro-latest"
                        logger.info(f"Error listing models. Defaulting to {self.config.model}")
                
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
        # Handle Gemini API
        if self.config.provider == LLMProvider.GEMINI.value:
            return self._gemini_chat_completion(messages, temperature, max_tokens, stream)
        
        # Inject reasoning effort into system prompts for reasoning models.
        messages = self._inject_reasoning_into_system(messages)
        
        # Convert messages to the format expected by the API
        formatted_messages = []
        
        # Special handling for models that don't support system messages
        if self.config.model in ["o1-mini", "deepseek-reasoner", "o3-mini", "o4-mini"]:
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
        
        # Handle temperature parameter
        supports_temperature = self.config.model not in ["o3-mini", "gpt-4o", "o4-mini"]
        if supports_temperature:
            if temperature is None:
                temperature = self.config.settings.temperature
            params["temperature"] = temperature
        
        # Handle max_tokens parameter with model-specific limits
        max_tokens = max_tokens or self.config.settings.max_tokens
        if max_tokens:
            # Apply model-specific token limits and parameter names
            if self.config.model == "gpt-4o":
                # GPT-4o has a 16k completion token limit
                max_tokens = min(max_tokens, 16000)
                params["max_completion_tokens"] = max_tokens
            elif self.config.model in ["o3-mini", "o4-mini"]:
                params["max_completion_tokens"] = max_tokens
            else:
                params["max_tokens"] = max_tokens
            
        try:
            logger.debug(f"LLM pre: Params: {params}")
            logger.info(f"Making API call to {self.config.provider}/{self.config.model}")
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
            
            # Log the exact model name being used for debugging
            logger.info(f"Sending request to Gemini model: {self.config.model}")
            
            try:
                # Create the model instance with the configured model
                model = self.client.GenerativeModel(model_name=self.config.model)
                
                # Get the last user message
                last_user_message = ""
                for msg in reversed(messages):
                    if msg.role == "user":
                        last_user_message = msg.content
                        break
                
                # Add system content if available
                if system_content:
                    last_user_message = system_content + "\n" + last_user_message
                
                # Generate the response
                logger.debug(f"Gemini pre: Using message: {last_user_message}, Config: {generation_config}")
                
                # Use generate_content which is more widely supported
                response = model.generate_content(
                    last_user_message,
                    generation_config=generation_config,
                    stream=stream
                )
                
                if stream:
                    full_response = ""
                    for chunk in response:
                        if hasattr(chunk, 'text'):
                            full_response += chunk.text
                    return full_response
                else:
                    return response.text
                    
            except Exception as model_error:
                # Log the detailed error
                error_message = str(model_error).lower()
                logger.error(f"Gemini error details: {str(model_error)}")
                
                # Special handling for quota issues - use the recommended model from error message
                if "429" in error_message and "gemini-2.5-pro-exp-03-25" in str(model_error):
                    logger.warning("Quota error with preview model, switching to experimental model")
                    try:
                        # Extract the recommended model name from the error message
                        recommended_model = "models/gemini-2.5-pro-exp-03-25"  # Directly using the recommended model
                        logger.info(f"Switching to recommended model: {recommended_model}")
                        
                        model = self.client.GenerativeModel(model_name=recommended_model)
                        
                        # Get the last user message again
                        last_user_message = ""
                        for msg in reversed(messages):
                            if msg.role == "user":
                                last_user_message = msg.content
                                break
                        
                        response = model.generate_content(
                            last_user_message,
                            generation_config=generation_config
                        )
                        
                        # Save the working model for future use
                        self.config.model = recommended_model
                        return response.text
                    except Exception as quota_error:
                        logger.error(f"Failed with recommended model: {str(quota_error)}")
                        # Continue to general fallback
                
                # Try another approach if the first one fails
                if "not found" in error_message or "not supported" in error_message or "429" in error_message:
                    logger.warning(f"Error with model {self.config.model}, trying to find an alternative model")
                    try:
                        # Get available models again to find alternatives - prioritize non-preview 2.5 models
                        models = self.client.list_models()
                        available_models = [model.name for model in models 
                                         if "generateContent" in model.supported_generation_methods]
                        
                        # First try experimental models, then 1.5 or others
                        prioritized_models = [m for m in available_models if "exp" in m and "2.5" in m]
                        if not prioritized_models:
                            prioritized_models = [m for m in available_models if "pro" in m]
                        
                        if prioritized_models:
                            fallback_model = prioritized_models[0]
                            logger.info(f"Using fallback model: {fallback_model}")
                            
                            model = self.client.GenerativeModel(model_name=fallback_model)
                            
                            # Get the last user message again
                            last_user_message = ""
                            for msg in reversed(messages):
                                if msg.role == "user":
                                    last_user_message = msg.content
                                    break
                            
                            response = model.generate_content(
                                last_user_message,
                                generation_config=generation_config
                            )
                            
                            # Save the working model for future use
                            self.config.model = fallback_model
                            return response.text
                        elif available_models:
                            # Last resort - any available model
                            fallback_model = available_models[0]
                            logger.info(f"Using any available model: {fallback_model}")
                            
                            model = self.client.GenerativeModel(model_name=fallback_model)
                            response = model.generate_content(
                                last_user_message,
                                generation_config=generation_config
                            )
                            
                            self.config.model = fallback_model
                            return response.text
                        else:
                            raise ValueError("No available Gemini models found")
                    except Exception as fallback_error:
                        raise Exception(f"Fallback attempt failed: {str(fallback_error)}")
                else:
                    # Some other error occurred
                    raise
                
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
            
        # IMPORTANT: Don't automatically switch models for vision - honor the configuration
        # Only log a warning if we're not using a known vision-capable model
        if self.config.model != "gpt-4o":
            logger.warning(f"Model {self.config.model} may not fully support vision capabilities. If you encounter errors, consider using gpt-4o.")
            
        # Process image with downscaling if needed and encode to base64
        try:
            with Image.open(image_path) as img:
                width, height = img.size
                max_dimension = self.config.settings.max_image_dimension
                if width > max_dimension or height > max_dimension:
                    scale = max_dimension / max(width, height)
                    new_width = int(width * scale)
                    new_height = int(height * scale)
                    img = img.resize((new_width, new_height))
                    logger.info(f"Image downscaled from ({width}x{height}) to ({new_width}x{new_height}).")
                else:
                    logger.info(f"Image size ({width}x{height}) within limits, no downscaling applied.")
                
                # Determine image format from file extension
                image_ext = os.path.splitext(image_path)[1].lower()
                if image_ext in ['.jpg', '.jpeg']:
                    mime_type = 'image/jpeg'
                    image_format = 'JPEG'
                elif image_ext == '.png':
                    mime_type = 'image/png'
                    image_format = 'PNG'
                else:
                    # Default to JPEG if unknown
                    mime_type = 'image/jpeg'
                    image_format = 'JPEG'
                
                buffer = BytesIO()
                img.save(buffer, format=image_format)
                image_bytes = buffer.getvalue()
                
            # Encode to base64
            base64_image = base64.b64encode(image_bytes).decode('utf-8')
            logger.info(f"Image encoded successfully: {image_path} as {mime_type}")
            
        except Exception as e:
            error_msg = f"Failed to process and encode image: {str(e)}"
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
                                "url": f"data:{mime_type};base64,{base64_image}"
                            }
                        }
                    ]
                })
            else:
                formatted_messages.append({
                    "role": msg.role,
                    "content": msg.content
                })
        
        # Prepare completion parameters - for vision models, only include necessary parameters
        params = {
            "model": self.config.model,
            "messages": formatted_messages,
            "stream": False,
            "timeout": self.config.settings.timeout,
        }
            
        try:
            # Create a sanitized copy of params for logging (without the image data)
            log_params = params.copy()
            if "messages" in log_params:
                log_params["messages"] = [
                    m if isinstance(m.get("content", ""), str) else 
                    {**m, "content": [
                        c if c.get("type") != "image_url" else {"type": "image_url", "image_url": {"url": "[BASE64_IMAGE_DATA]"}}
                        for c in m.get("content", [])
                    ]}
                    for m in log_params["messages"]
                ]
            
            logger.debug(f"Vision LLM pre: Params: {log_params}")
            response = self.client.chat.completions.create(**params)
            logger.debug(f"Vision LLM post: Response received: {response}")
            
            if not response or not response.choices:
                raise ValueError("Empty response received from API")
                
            return response.choices[0].message.content
        except Exception as e:
            provider_name = self.config.provider.capitalize()
            # Add more detailed error information
            error_msg = f"{provider_name} vision API call failed: {str(e)}"
            if hasattr(e, 'response'):
                error_msg += f"\nResponse status: {e.response.status_code}"
                try:
                    error_msg += f"\nResponse body: {e.response.text}"
                except:
                    pass
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
            
            # Get the model - try with a vision-capable model if current model fails
            logger.debug(f"Using Gemini model for vision: {self.config.model}")
            
            try:
                model = self.client.GenerativeModel(model_name=self.config.model)
                
                # Generate the response
                logger.debug(f"Gemini Vision pre: Text: {user_message}, Config: {generation_config}")
                response = model.generate_content(
                    contents,
                    generation_config=generation_config
                )
                logger.debug(f"Gemini Vision post: Response received")
                
                return response.text
            except Exception as vision_error:
                # If current model doesn't support vision, try to find a vision-capable model
                if "not supported" in str(vision_error) or "not found" in str(vision_error):
                    logger.warning(f"Model {self.config.model} doesn't support vision. Looking for alternatives...")
                    
                    try:
                        # Check available models for vision capability
                        models = self.client.list_models()
                        vision_models = [model.name for model in models 
                                        if "generateContent" in model.supported_generation_methods 
                                        and hasattr(model, "supported_generation_methods") 
                                        and getattr(model, "input_mime_types", [])
                                        and any("image/" in mime_type for mime_type in getattr(model, "input_mime_types", []))]
                        
                        if vision_models:
                            fallback_model_name = vision_models[0]
                            logger.info(f"Using vision-capable model: {fallback_model_name}")
                            
                            fallback_model = self.client.GenerativeModel(model_name=fallback_model_name)
                            response = fallback_model.generate_content(
                                contents,
                                generation_config=generation_config
                            )
                            return response.text
                        else:
                            return f"Vision LLM failure: No vision-capable Gemini models available"
                    except Exception as fallback_error:
                        return f"Vision LLM failure: {str(vision_error)}. Fallback attempt also failed: {str(fallback_error)}"
                else:
                    raise
                
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
        # Example usage with specific template (component-based)
    client_component = LLMClient(component="protoblock_generation")  # Will use o4-mini
    component_response = client_component.chat_completion([
        Message(role="system", content="You are a helpful assistant."),
        Message(role="user", content="What are three interesting Python features?")
    ])
    print(f"\nComponent-based template (native_agent) response:")
    print(component_response)
    
    # Example with vision model
    print("\nUsing vision model:")
    # image_path = os.path.expanduser("~/Downloads/tmpip7ugsgv.png")
    image_path = os.path.expanduser("~/Downloads/tmpig4ajga7.png")
    # Check if the image exists
    if os.path.exists(image_path):
        client_vision = LLMClient(component="vision")  # Use component="vision" which maps to gpt-4o
        vision_messages = [
            Message(role="system", content="You are a helpful assistant that can analyze images"),
            Message(role="user", content="Do you see a white background and a blue dot in the middle?")
        ]
        print(f"Analyzing image at: {image_path}")
        response_vision = client_vision.vision_chat_completion(vision_messages, image_path)
        print(response_vision)
    else:
        print(f"Image not found at {image_path}. Vision example skipped.") 
        
    # Example usage with component-based configuration
    client_default = LLMClient(component="chat")
    default_response = client_default.chat_completion([
        Message(role="user", content="What is the capital of France?")
    ])
    print(f"Default response: {default_response}")
    

    
    # Example usage with Gemini model (component-based)
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    if gemini_api_key:
        print("\nGemini API key found, running Gemini example...")
        try:
            # Component-based approach - using the "gemini" component (which maps to gemini-2.5-pro)
            client_gemini = LLMClient(component="gemini")
            
            gemini_response = client_gemini.chat_completion([
                Message(role="system", content="You are a helpful assistant who provides concise answers."),
                Message(role="user", content="What are three key benefits of AI in healthcare?")
            ])
            
            print("\nResponse from Gemini 2.5 Pro (component='gemini'):")
            print("-" * 50)
            print(gemini_response)
            print("-" * 50)
            
            # List available Gemini models (if needed)
            import google.generativeai as genai
            genai.configure(api_key=gemini_api_key)
            models = genai.list_models()
            available_models = [model.name for model in models if "generateContent" in model.supported_generation_methods]
            print(f"Available Gemini models: {available_models}")
            
            # Check if 2.5 Pro is available or fallback
            gemini_25_pro = [m for m in available_models if "gemini-2.5-pro" in m]
            if not gemini_25_pro:
                print("\nNote: Gemini 2.5 Pro not found in your available models.")
                
                # Find best available Gemini model for fallback
                if available_models:
                    # Look for latest Pro models (prioritize newer versions)
                    pro_models = [m for m in available_models if "pro" in m]
                    latest_models = [m for m in pro_models if "latest" in m]
                    
                    if latest_models:
                        fallback_model = latest_models[0]
                    elif pro_models:
                        fallback_model = pro_models[0]
                    else:
                        fallback_model = available_models[0]
                    
                    print(f"Using fallback model: {fallback_model}")
                    print("Your component config will still specify 2.5 Pro, which will be used when available.")
                    print("If you want to use Gemini 2.5 Pro, you may need to:")
                    print("1. Upgrade your Google AI API plan")
                    print("2. Request access to the model if it's in limited preview")
                    print("3. Check if 'gemini-2.5-pro' is available in your region")
                    
                    # Example with direct fallback override
                    print("\nTesting fallback with direct override...")
                    client_fallback = LLMClient(config_override={
                        "provider": "gemini", 
                        "model": fallback_model,
                        "api_key": gemini_api_key
                    })
                    
                    fallback_response = client_fallback.chat_completion([
                        Message(role="system", content="You are a helpful assistant who provides concise answers."),
                        Message(role="user", content="What are three examples of emerging AI technologies?")
                    ])
                    
                    print(f"\nResponse from fallback model ({fallback_model}):")
                    print("-" * 50)
                    print(fallback_response)
                    print("-" * 50)
            else:
                print(f"\nConfirmed Gemini 2.5 Pro is available: {gemini_25_pro[0]}")
            
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
            
    # Print the o3-mini template definition
    o3_mini_template = config._config.llm_templates.get("o3-mini")
    print("\nDirect o3-mini template inspection:")
    print("-" * 50)
    if o3_mini_template:
        print(f"Template: o3-mini")
        print(f"Provider: {o3_mini_template.provider}")
        print(f"Model: {o3_mini_template.model}")
        print(f"Settings: {vars(o3_mini_template.settings)}")
    else:
        print("o3-mini template not found!") 