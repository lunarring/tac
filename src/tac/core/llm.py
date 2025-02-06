"""Module for handling LLM (Language Model) interactions."""

import os
from enum import Enum
from typing import List, Dict, Optional, Union
from dataclasses import dataclass
import yaml

from openai import OpenAI
from openai.types.chat import ChatCompletion

class LLMProvider(Enum):
    """Supported LLM providers."""
    DEEPSEEK = "deepseek"
    OPENAI = "openai"

@dataclass
class Message:
    """Represents a chat message."""
    role: str
    content: str

class LLMConfig:
    """Configuration for LLM clients."""
    
    @staticmethod
    def from_config_file(config_path: Optional[str] = None, strength: str = "weak") -> 'LLMConfig':
        """Create LLMConfig from config.yaml file.
        
        Args:
            config_path: Path to config file
            strength: Whether to use strong or weak LLM ("strong" or "weak", defaults to "weak")
        """
        if config_path is None:
            # Use the same config path resolution as main CLI
            config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'config.yaml')
            
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Could not find config file at: {config_path}")
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        config_key = f"llm_{strength}"
        llm_config = config.get(config_key, {})
        provider = llm_config.get('provider', 'deepseek')  # Default to deepseek
        model = llm_config.get('model', 'deepseek-chat')
        
        return LLMConfig(provider=provider, model=model, settings=llm_config.get('settings', {}))
    
    def __init__(self, provider: Union[LLMProvider, str], model: str, settings: Optional[Dict] = None):
        if isinstance(provider, str):
            provider = LLMProvider(provider.lower())
        self.provider = provider
        self.model = model
        self.settings = settings or {}
        
        # Load API keys from environment variables
        if provider == LLMProvider.DEEPSEEK:
            self.api_key = os.getenv("DEEPSEEK_API_KEY")
            if not self.api_key:
                raise ValueError("DEEPSEEK_API_KEY environment variable not set")
            self.base_url = "https://api.deepseek.com"
        else:  # OpenAI
            self.api_key = os.getenv("OPENAI_API_KEY")
            if not self.api_key:
                raise ValueError("OPENAI_API_KEY environment variable not set")
            self.base_url = None  # OpenAI uses default base URL

class LLMClient:
    """Client for interacting with Language Models."""
    
    def __init__(self, config: Optional[LLMConfig] = None, strength: str = "weak"):
        """Initialize client with config from file or provided config.
        
        Args:
            config: Optional LLMConfig instance
            strength: Whether to use strong or weak LLM ("strong" or "weak", defaults to "weak")
        """
        self.config = config or LLMConfig.from_config_file(strength=strength)
        self.client = self._initialize_client()
    
    def _initialize_client(self) -> OpenAI:
        """Initialize the OpenAI client with appropriate configuration."""
        kwargs = {
            "api_key": self.config.api_key,
            "timeout": self.config.settings.get('timeout', 120),
        }
        if self.config.base_url:
            kwargs["base_url"] = self.config.base_url
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
        if self.config.model in ["o1-mini", "deepseek-reasoner"]:
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
            "timeout": self.config.settings.get('timeout', 120),
        }
        
        # Models that don't support temperature parameter
        if self.config.model not in ["o1-mini", "deepseek-reasoner"] and "o3-mini" not in self.config.model:
            # Use settings from config if not overridden
            if temperature is None:
                temperature = self.config.settings.get('temperature', 0.7)
            params["temperature"] = temperature
        
        if max_tokens is None:
            max_tokens = self.config.settings.get('max_tokens')
        if max_tokens:
            params["max_tokens"] = max_tokens
            
        try:
            response = self.client.chat.completions.create(**params)
            if not response or not response.choices:
                raise ValueError("Empty response received from API")
            return response.choices[0].message.content
        except Exception as e:
            provider_name = self.config.provider.value.capitalize()
            # Add more detailed error information
            error_msg = f"{provider_name} API call failed: {str(e)}"
            if hasattr(e, 'response'):
                error_msg += f"\nResponse status: {e.response.status_code}"
                try:
                    error_msg += f"\nResponse body: {e.response.text}"
                except:
                    pass
            return f"LLM failure: {error_msg}"

# Example usage:
if __name__ == "__main__":
    # Create manual config
    config = LLMConfig(
        provider="deepseek",
        model="deepseek-reasoner",
        settings={"timeout": 120}
    )
    
    # Create client with manual config
    client = LLMClient(config=config)
    
    # Example messages
    messages = [
        Message(role="system", content="You are a helpful assistant"),
        Message(role="user", content="Hello!")
    ]
    
    # Get completion
    response = client.chat_completion(messages)
    print(response)  # Now directly prints the message content 
