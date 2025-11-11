"""OpenAI Model Implementation"""

from typing import Dict, List
from loguru import logger
from .base_model import BaseLLM


class OpenAIModel(BaseLLM):
    """OpenAI GPT model implementation"""

    def __init__(self, config: Dict):
        """Initialize OpenAI model"""
        super().__init__(config)

        # Extract OpenAI-specific settings
        self.api_key = config.get("api_key")
        self.model = config.get("model", "gpt-4")
        self.temperature = config.get("temperature", 0.1)
        self.max_tokens = config.get("max_tokens", 4096)

        # Validate API key
        if not self.api_key:
            logger.warning("OpenAI API key not provided in config")

        # Import here to avoid hard dependency
        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=self.api_key)
        except ImportError:
            logger.warning("OpenAI package not installed. Install with: pip install openai")
            self.client = None

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate response from prompt"""
        if not self.client:
            logger.error("OpenAI client not initialized")
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
            logger.error(f"OpenAI API error: {e}")
            return ""

    def generate_with_system(self, system: str, user: str, **kwargs) -> str:
        """Generate response with system and user messages"""
        if not self.client:
            logger.error("OpenAI client not initialized")
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
            logger.error(f"OpenAI API error: {e}")
            return ""

    def chat(self, messages: List[Dict], **kwargs) -> str:
        """Generate response from chat messages"""
        if not self.client:
            logger.error("OpenAI client not initialized")
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
            logger.error(f"OpenAI API error: {e}")
            return ""

