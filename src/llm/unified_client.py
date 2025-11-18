"""Unified LLM Client - Universal API for all LLM providers"""

from typing import Dict, List, Optional, Any


class UnifiedLLMClient:
    """
    Unified LLM Client using standard chat completion API.
    
    Works with any LLM service that provides compatible API interface.
    Only requires base_url and api_key configuration.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize unified LLM client
        
        Args:
            config: Configuration dict with:
                - base_url: API endpoint URL
                - api_key: API authentication key
                - model: Model name/identifier
                - temperature: Sampling temperature (default: 0.1)
                - max_tokens: Maximum tokens to generate (default: 4096)
        """
        self.config = config or {}
        self.base_url = self.config.get('base_url', '')
        self.api_key = self.config.get('api_key', '')
        self.model = self.config.get('model', 'default')
        self.temperature = self.config.get('temperature', 0.1)
        self.max_tokens = self.config.get('max_tokens', 4096)
        
        self.client = self._initialize_client()
    
    def _initialize_client(self):
        """Initialize the HTTP client"""
        if not self.base_url or not self.api_key:
            print("Warning: base_url or api_key not provided")
            return None
        
        try:
            # Use standard HTTP client library
            from openai import OpenAI
            return OpenAI(
                base_url=self.base_url,
                api_key=self.api_key
            )
        except Exception as e:
            print(f"Error initializing client: {e}")
            return None
    
    def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate response from a single prompt
        
        Args:
            prompt: Input prompt text
            **kwargs: Additional parameters (temperature, max_tokens)
            
        Returns:
            Generated response text
        """
        if not self.client:
            return ""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=kwargs.get("temperature", self.temperature),
                max_tokens=kwargs.get("max_tokens", self.max_tokens),
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"API error: {e}")
            return ""
    
    def generate_with_system(self, system: str, user: str, **kwargs) -> str:
        """
        Generate response with system and user messages
        
        Args:
            system: System message (instructions, context)
            user: User message (actual query)
            **kwargs: Additional parameters
            
        Returns:
            Generated response text
        """
        if not self.client:
            return ""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=kwargs.get("temperature", self.temperature),
                max_tokens=kwargs.get("max_tokens", self.max_tokens),
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"API error: {e}")
            return ""
    
    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """
        Generate response from chat message history
        
        Args:
            messages: List of message dicts [{"role": "user", "content": "..."}]
            **kwargs: Additional parameters
            
        Returns:
            Generated response text
        """
        if not self.client:
            return ""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=kwargs.get("temperature", self.temperature),
                max_tokens=kwargs.get("max_tokens", self.max_tokens),
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"API error: {e}")
            return ""
    
    def update_config(self, config: Dict[str, Any]):
        """
        Update client configuration
        
        Args:
            config: New configuration parameters
        """
        self.config.update(config)
        
        if 'base_url' in config:
            self.base_url = config['base_url']
        if 'api_key' in config:
            self.api_key = config['api_key']
        if 'model' in config:
            self.model = config['model']
        if 'temperature' in config:
            self.temperature = config['temperature']
        if 'max_tokens' in config:
            self.max_tokens = config['max_tokens']
        
        # Reinitialize client if base_url or api_key changed
        if 'base_url' in config or 'api_key' in config:
            self.client = self._initialize_client()
    
    @property
    def current_model(self) -> str:
        """Get current model name"""
        return self.model
    
    @property
    def is_initialized(self) -> bool:
        """Check if client is properly initialized"""
        return self.client is not None


# Convenience functions
def create_client(base_url: str, api_key: str, model: str = "default", **kwargs) -> UnifiedLLMClient:
    """
    Create a new LLM client
    
    Args:
        base_url: API endpoint URL
        api_key: API authentication key
        model: Model name/identifier
        **kwargs: Additional configuration (temperature, max_tokens)
    
    Returns:
        Configured UnifiedLLMClient
    
    Example:
        client = create_client(
            base_url="https://api.example.com/v1",
            api_key="sk-...",
            model="gpt-4",
            temperature=0.2
        )
        response = client.generate("Write a sorting algorithm")
    """
    config = {
        'base_url': base_url,
        'api_key': api_key,
        'model': model,
        **kwargs
    }
    return UnifiedLLMClient(config)


# Singleton for default client
_default_client: Optional[UnifiedLLMClient] = None


def get_default_client() -> UnifiedLLMClient:
    """
    Get the default LLM client
    
    Returns:
        Default UnifiedLLMClient instance
    """
    global _default_client
    if _default_client is None:
        raise RuntimeError("Default client not set. Call set_default_client() first.")
    return _default_client


def set_default_client(client: UnifiedLLMClient):
    """
    Set the default LLM client
    
    Args:
        client: UnifiedLLMClient instance to set as default
    """
    global _default_client
    _default_client = client
