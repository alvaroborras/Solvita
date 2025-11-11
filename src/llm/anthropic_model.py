"""Anthropic Claude Model Implementation"""

from typing import Dict, List
from loguru import logger
from .base_model import BaseLLM


class AnthropicModel(BaseLLM):
    """Anthropic Claude model implementation"""

    def __init__(self, config: Dict):
        """Initialize Anthropic model"""
        super().__init__(config)

        # Extract Anthropic-specific settings
        self.api_key = config.get("api_key")
        self.model = config.get("model", "claude-3-sonnet-20240229")
        self.temperature = config.get("temperature", 0.1)
        self.max_tokens = config.get("max_tokens", 4096)

        # Validate API key
        if not self.api_key:
            logger.warning("Anthropic API key not provided in config")

        # Import here to avoid hard dependency
        try:
            from anthropic import Anthropic
            self.client = Anthropic(api_key=self.api_key)
        except ImportError:
            logger.warning("Anthropic package not installed. Install with: pip install anthropic")
            self.client = None

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate response from prompt"""
        if not self.client:
            logger.error("Anthropic client not initialized")
            return ""

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=kwargs.get("max_tokens", self.max_tokens),
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            return ""

    def generate_with_system(self, system: str, user: str, **kwargs) -> str:
        """Generate response with system and user messages"""
        if not self.client:
            logger.error("Anthropic client not initialized")
            return ""

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=kwargs.get("max_tokens", self.max_tokens),
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return message.content[0].text
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            return ""

    def chat(self, messages: List[Dict], **kwargs) -> str:
        """Generate response from chat messages"""
        if not self.client:
            logger.error("Anthropic client not initialized")
            return ""

        try:
            # Extract system message if present
            system_message = None
            chat_messages = []

            for msg in messages:
                if msg.get("role") == "system":
                    system_message = msg.get("content", "")
                else:
                    chat_messages.append(msg)

            # Build the request
            kwargs_api = {"model": self.model, "max_tokens": kwargs.get("max_tokens", self.max_tokens), "messages": chat_messages}

            if system_message:
                kwargs_api["system"] = system_message

            message = self.client.messages.create(**kwargs_api)
            return message.content[0].text
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            return ""

