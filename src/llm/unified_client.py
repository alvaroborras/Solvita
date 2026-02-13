"""Unified LLM Client - Universal API for all LLM providers"""

import os
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any
from loguru import logger


class UnifiedLLMClient:
    """
    Unified LLM Client using standard chat completion API.
    
    Works with any LLM service that provides compatible API interface.

    Configuration resolution order (first match wins):
      1. Explicit keys in *config* dict (base_url, api_key, model ...)
      2. config/models.yaml  (looked up relative to project root)
      3. Environment variables: SOLVITA_BASE_URL, SOLVITA_API_KEY, SOLVITA_MODEL
    
    Raises ConfigurationError if neither base_url nor api_key can be resolved.
    """
    
    class ConfigurationError(RuntimeError):
        """Raised when required LLM configuration is missing."""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self._resolved = self._resolve_config()

        self.base_url: str = self._resolved["base_url"]
        self.api_key: str = self._resolved["api_key"]
        self.model: str = self._resolved["model"]
        self.temperature: float = self._resolved["temperature"]
        self.max_tokens: int = self._resolved["max_tokens"]

        self.client = self._initialize_client()

        # Default values
        self.base_url = self.config.get('base_url', 'http://14.103.68.46/v1')
        self.api_key = self.config.get('api_key', 'sk-<redacted>')
        self.model = self.config.get('model', 'claude-opus-4-5-20251101')
        self.temperature = self.config.get('temperature', 0.1)
        self.max_tokens = self.config.get('max_tokens', 128000)

    def _resolve_config(self) -> Dict[str, Any]:
        """Merge config dict -> YAML file -> env vars, fail if incomplete."""
        # Start with defaults for non-critical fields
        resolved: Dict[str, Any] = {
            "base_url": "",
            "api_key": "",
            "model": "gpt-4",
            "temperature": 0.1,
            "max_tokens": 128000,
        }

        # Layer 1: YAML file (lowest priority for base_url/api_key)
        yaml_cfg = self._load_yaml_config()
        if yaml_cfg:
            for key in resolved:
                if key in yaml_cfg:
                    resolved[key] = yaml_cfg[key]

        # Layer 2: Environment variables
        env_map = {
            "base_url": "SOLVITA_BASE_URL",
            "api_key": "SOLVITA_API_KEY",
            "model": "SOLVITA_MODEL",
        }
        for key, env_key in env_map.items():
            val = os.environ.get(env_key)
            if val:
                resolved[key] = val

        # Layer 3: Explicit config dict (highest priority)
        for key in resolved:
            if key in self.config and self.config[key]:
                resolved[key] = self.config[key]

        # Validate required fields
        if not resolved["base_url"] or not resolved["api_key"]:
            raise self.ConfigurationError(
                "LLM configuration incomplete. Provide base_url and api_key via one of:\n"
                "  1. config dict passed to UnifiedLLMClient\n"
                "  2. config/models.yaml (llm.base_url / llm.api_key)\n"
                "  3. Environment variables SOLVITA_BASE_URL / SOLVITA_API_KEY"
            )

        return resolved

    @staticmethod
    def _load_yaml_config() -> Optional[Dict[str, Any]]:
        """Try to load LLM config from config/models.yaml."""
        # Try project-relative path first, then absolute
        candidates = [
            Path("config/models.yaml"),
            Path(__file__).resolve().parents[2] / "config" / "models.yaml",
        ]
        for config_path in candidates:
            if config_path.exists():
                try:
                    with open(config_path, "r") as f:
                        data = yaml.safe_load(f)
                    if data and "llm" in data:
                        return data["llm"]
                except Exception as e:
                    logger.warning(f"Failed to load config from {config_path}: {e}")
        return None



    def _initialize_client(self):
        """Initialize the OpenAI-compatible HTTP client."""
        try:
            from openai import OpenAI
            return OpenAI(base_url=self.base_url, api_key=self.api_key)
        except Exception as e:
            logger.error(f"Error initializing LLM client: {e}")
            return None


    def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate response from a single prompt.

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
                model=kwargs.get("model", self.model),
                messages=[{"role": "user", "content": prompt}],
                temperature=kwargs.get("temperature", self.temperature),
                max_tokens=kwargs.get("max_tokens", self.max_tokens),
            )
            if isinstance(response, str):
                return response
            content = response.choices[0].message.content
            return content if content is not None else ""
        except Exception as e:
            logger.error(f"LLM API error: {e}")
            return ""
    
    def generate_with_system(self, system: str, user: str, **kwargs) -> str:
        """Generate response with system and user messages."""
        if not self.client:
            return ""

        try:
            response = self.client.chat.completions.create(
                model=kwargs.get("model", self.model),
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=kwargs.get("temperature", self.temperature),
                max_tokens=kwargs.get("max_tokens", self.max_tokens),
            )
            if isinstance(response, str):
                return response
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"LLM API error: {e}")
            return ""
    
    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """Generate response from chat message history."""
        if not self.client:
            return ""

        try:
            response = self.client.chat.completions.create(
                model=kwargs.get("model", self.model),
                messages=messages,
                temperature=kwargs.get("temperature", self.temperature),
                max_tokens=kwargs.get("max_tokens", self.max_tokens),
            )
            if isinstance(response, str):
                return response
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"LLM API error: {e}")
            return ""
    
    def update_config(self, config: Dict[str, Any]):
        """Update client configuration at runtime."""
        self.config.update(config)
        if "base_url" in config:
            self.base_url = config["base_url"]
        if "api_key" in config:
            self.api_key = config["api_key"]
        if "model" in config:
            self.model = config["model"]
        if "temperature" in config:
            self.temperature = config["temperature"]
        if "max_tokens" in config:
            self.max_tokens = config["max_tokens"]
        if "base_url" in config or "api_key" in config:
            self.client = self._initialize_client()

    @property
    def current_model(self) -> str:
        return self.model
    
    @property
    def is_initialized(self) -> bool:
        return self.client is not None



def create_client(base_url: str, api_key: str, model: str = "gpt-4", **kwargs) -> UnifiedLLMClient:
    """Create a new LLM client with explicit credentials."""
    config = {"base_url": base_url, "api_key": api_key, "model": model, **kwargs}
    return UnifiedLLMClient(config)


_default_client: Optional[UnifiedLLMClient] = None


def get_default_client() -> UnifiedLLMClient:
    """Get the default LLM client (must call set_default_client first)."""
    global _default_client
    if _default_client is None:
        raise RuntimeError("Default client not set. Call set_default_client() first.")
    return _default_client


def set_default_client(client: UnifiedLLMClient):
    """Set the default LLM client singleton."""
    global _default_client
    _default_client = client
