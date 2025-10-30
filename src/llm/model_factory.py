"""LLM Model Factory"""

from typing import Dict, Any
from .base_model import BaseLLM


class ModelFactory:
    """Factory for creating LLM model instances"""

    @staticmethod
    def create(model_name: str, config: Dict[str, Any] = None) -> BaseLLM:
        """
        Create LLM model instance.

        Args:
            model_name: Model name (gpt-4, claude-3-sonnet, etc.)
            config: Optional configuration dict

        Returns:
            LLM model instance
        """
        config = config or {}

        # Determine provider from model name
        if 'gpt' in model_name.lower():
            from .openai_model import OpenAIModel
            return OpenAIModel(config)
        elif 'claude' in model_name.lower():
            from .anthropic_model import AnthropicModel
            return AnthropicModel(config)
        else:
            # Fallback to mock LLM for development
            return MockLLM(config)

    @staticmethod
    def create_model(model_type: str, config: Dict) -> BaseLLM:
        """Legacy method for backwards compatibility"""
        return ModelFactory.create(model_type, config)


class MockLLM(BaseLLM):
    """Mock LLM for testing without API keys"""

    def __init__(self, config: Dict):
        self.config = config

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate mock response"""
        return "// Mock LLM response - replace with real LLM"

    def generate_with_system(self, system: str, user: str, **kwargs) -> str:
        """Generate mock response with system message"""
        return "// Mock LLM response - replace with real LLM"

    def chat(self, messages: list, **kwargs) -> str:
        """Generate mock response from chat"""
        return "// Mock LLM response - replace with real LLM"

