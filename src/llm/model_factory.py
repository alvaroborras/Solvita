"""LLM Model Factory"""

from typing import Dict
from .base_model import BaseLLM
from .openai_model import OpenAIModel
from .anthropic_model import AnthropicModel
from .local_model import LocalModel


class ModelFactory:
    """Factory for creating LLM model instances"""
    
    @staticmethod
    def create_model(model_type: str, config: Dict) -> BaseLLM:
        """
        Create LLM model instance
        
        Args:
            model_type: Type of model (openai, anthropic, local)
            config: Model configuration
            
        Returns:
            LLM model instance
        """
        pass

