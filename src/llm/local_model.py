"""Local Model Implementation"""

from typing import Dict, List
from .base_model import BaseLLM


class LocalModel(BaseLLM):
    """Local open-source model implementation"""
    
    def __init__(self, config: Dict):
        """Initialize local model"""
        super().__init__(config)
    
    def generate(self, prompt: str, **kwargs) -> str:
        """Generate response from prompt"""
        pass
    
    def generate_with_system(self, system: str, user: str, **kwargs) -> str:
        """Generate response with system and user messages"""
        pass
    
    def chat(self, messages: List[Dict], **kwargs) -> str:
        """Generate response from chat messages"""
        pass

