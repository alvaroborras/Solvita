"""Base LLM Model Interface"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class BaseLLM(ABC):
    """Abstract base class for LLM models"""

    def __init__(self, config: Dict):
        """Initialize LLM model"""
        self.config = config or {}
    
    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> str:
        """Generate response from prompt"""
        pass
    
    @abstractmethod
    def generate_with_system(self, system: str, user: str, **kwargs) -> str:
        """Generate response with system and user messages"""
        pass
    
    @abstractmethod
    def chat(self, messages: List[Dict], **kwargs) -> str:
        """Generate response from chat messages"""
        pass

