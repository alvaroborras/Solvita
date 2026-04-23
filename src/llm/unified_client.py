"""Unified LLM Client - Universal API for all LLM providers"""

import os
import shutil
import sys
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any
from loguru import logger

from .token_usage import (
    ensure_token_usage_accumulator,
    estimate_message_tokens,
    estimate_text_tokens,
    extract_completion_text,
    extract_usage_counts,
    get_token_usage_snapshot,
    record_token_usage,
)


class FatalLLMError(Exception):
    """全局性致命 LLM 错误（如令牌额度耗尽、鉴权失败、限流），表示训练不可继续。"""


class PromptTooLongError(ValueError):
    """Raised when the upstream API rejects a request because the prompt exceeded max context."""


# 关键字集合：命中任一则视为 fatal (中英文均覆盖)
# Note: 429 / rate limit are NOT fatal — the SDK retries them automatically.
# Only truly unrecoverable errors belong here.
_FATAL_KEYWORDS = (
    # English
    "quota", "401", "403",
    "unauthorized", "forbidden", "auth", "billing",
    "insufficient_quota",
    # 中文（来自真实 API 响应）
    "额度已用尽", "额度", "令牌",
)


def _check_and_raise_fatal(exc: Exception) -> None:
    """如果 exc 的字符串描述含有致命关键字，则抛出 FatalLLMError；否则静默返回。"""
    err_str = str(exc).lower()
    if any(k in err_str for k in _FATAL_KEYWORDS):
        raise FatalLLMError(str(exc)) from exc


def _check_and_raise_prompt_too_long(exc: Exception) -> None:
    err_str = str(exc).lower()
    markers = (
        "prompt is too long",
        "maximum context length",
        "too many tokens",
        "tokens >",
        "maximum",
    )
    if "prompt" in err_str and any(marker in err_str for marker in markers):
        raise PromptTooLongError(str(exc)) from exc


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
        self.request_timeout: Optional[float] = self._resolved["request_timeout"]
        self.provider: str = str(self._resolved.get("provider") or "openai").strip().lower()

        self._usage_accumulator = ensure_token_usage_accumulator(self.config)
        self._last_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "token_usage_source": "untracked",
        }
        self.client = self._initialize_client()

    @staticmethod
    def _config_candidates(config: Dict[str, Any]) -> List[Path]:
        candidates: List[Path] = []

        cfg_path = config.get("config_path")
        if cfg_path:
            p = Path(cfg_path)
            candidates.append(p / "models.yaml" if p.is_dir() else p)

        env_cfg_path = os.environ.get("SOLVITA_CONFIG_PATH")
        if env_cfg_path:
            p = Path(env_cfg_path)
            candidates.append(p / "models.yaml" if p.is_dir() else p)

        candidates.extend(
            [
                Path("config/models.yaml"),
                Path(__file__).resolve().parents[2] / "config" / "models.yaml",
            ]
        )

        deduped: List[Path] = []
        seen = set()
        for item in candidates:
            key = str(item.resolve()) if item.exists() else str(item)
            if key not in seen:
                deduped.append(item)
                seen.add(key)
        return deduped

    @classmethod
    def _load_yaml_root(cls, config: Dict[str, Any]) -> Dict[str, Any]:
        """Try to load YAML root config from config/models.yaml."""
        for config_path in cls._config_candidates(config):
            if config_path.exists():
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                    if isinstance(data, dict):
                        return data
                except Exception as e:
                    logger.warning(f"Failed to load config from {config_path}: {e}")
        return {}

    @classmethod
    def resolve_role_overrides(cls, config: Dict[str, Any], role: str) -> Dict[str, Any]:
        """Resolve per-role LLM overrides from runtime config and YAML."""
        role_overrides: Dict[str, Any] = {}
        yaml_root = cls._load_yaml_root(config)
        prefer_runtime_overrides = cls._has_runtime_llm_overrides(config)

        llm_section = yaml_root.get("llm", {}) if isinstance(yaml_root, dict) else {}
        yaml_roles = llm_section.get("roles", {}) if isinstance(llm_section, dict) else {}
        if not prefer_runtime_overrides and role in yaml_roles:
            value = yaml_roles[role]
            if isinstance(value, dict):
                role_overrides.update(value)
            elif isinstance(value, str):
                role_overrides["model"] = value

        yaml_roles_legacy = yaml_root.get("llm_roles", {}) if isinstance(yaml_root, dict) else {}
        if not prefer_runtime_overrides and role in yaml_roles_legacy:
            value = yaml_roles_legacy[role]
            if isinstance(value, dict):
                role_overrides.update(value)
            elif isinstance(value, str):
                role_overrides["model"] = value

        cfg_roles = config.get("llm_roles", {}) if isinstance(config, dict) else {}
        if role in cfg_roles:
            value = cfg_roles[role]
            if isinstance(value, dict):
                role_overrides.update(value)
            elif isinstance(value, str):
                role_overrides["model"] = value

        return role_overrides

    @staticmethod
    def _has_runtime_llm_overrides(config: Dict[str, Any]) -> bool:
        keys = (
            "base_url",
            "api_key",
            "model",
            "temperature",
            "max_tokens",
            "request_timeout",
            "azure_tenant_id",
            "azure_scope",
            "api_version",
        )
        if isinstance(config, dict) and any(config.get(key) for key in keys):
            return True

        env_keys = (
            "SOLVITA_BASE_URL",
            "SOLVITA_API_KEY",
            "SOLVITA_MODEL",
            "SOLVITA_TEMPERATURE",
            "SOLVITA_MAX_TOKENS",
            "SOLVITA_REQUEST_TIMEOUT",
            "SOLVITA_AZURE_TENANT_ID",
            "SOLVITA_AZURE_SCOPE",
            "SOLVITA_AZURE_API_VERSION",
        )
        return any(os.environ.get(key) for key in env_keys)

    @staticmethod
    def _looks_like_azure_base_url(base_url: str) -> bool:
        url = (base_url or "").lower()
        return "azure" in url or ".azure-api.net" in url or ".openai.azure.com" in url

    @classmethod
    def build_role_config(cls, config: Dict[str, Any], role: str) -> Dict[str, Any]:
        role_cfg = dict(config or {})
        role_cfg.update(cls.resolve_role_overrides(role_cfg, role))
        return role_cfg

    def _resolve_config(self) -> Dict[str, Any]:
        """Merge config dict -> YAML file -> env vars, fail if incomplete."""
        # Start with defaults for non-critical fields
        resolved: Dict[str, Any] = {
            "base_url": "",
            "api_key": "",
            "model": "",
            "temperature": 0.1,
            "max_tokens": 128000,
            "request_timeout": 180,
            "azure_tenant_id": "",
            "azure_scope": "",
            "api_version": "",
            "provider": "openai",
        }

        # Layer 1: YAML file (lowest priority for base_url/api_key)
        yaml_root = self._load_yaml_root(self.config)
        yaml_cfg = yaml_root.get("llm", {}) if isinstance(yaml_root, dict) else {}
        if yaml_cfg:
            for key in resolved:
                if key in yaml_cfg:
                    resolved[key] = yaml_cfg[key]

        # Layer 2: Environment variables
        env_map = {
            "base_url": "SOLVITA_BASE_URL",
            "api_key": "SOLVITA_API_KEY",
            "model": "SOLVITA_MODEL",
            "temperature": "SOLVITA_TEMPERATURE",
            "max_tokens": "SOLVITA_MAX_TOKENS",
            "request_timeout": "SOLVITA_REQUEST_TIMEOUT",
            "azure_tenant_id": "SOLVITA_AZURE_TENANT_ID",
            "azure_scope": "SOLVITA_AZURE_SCOPE",
            "api_version": "SOLVITA_AZURE_API_VERSION",
            "provider": "SOLVITA_PROVIDER",
        }
        legacy_env_provider = os.environ.get("SOLVITA_LLM_PROVIDER")
        for key, env_key in env_map.items():
            val = os.environ.get(env_key)
            if key == "provider" and not val and legacy_env_provider:
                val = legacy_env_provider
            if val:
                if key == "temperature":
                    try:
                        resolved[key] = float(val)
                    except ValueError:
                        logger.warning(f"Invalid {env_key}: {val}")
                elif key == "max_tokens":
                    try:
                        resolved[key] = int(val)
                    except ValueError:
                        logger.warning(f"Invalid {env_key}: {val}")
                elif key == "request_timeout":
                    try:
                        resolved[key] = float(val)
                    except ValueError:
                        logger.warning(f"Invalid {env_key}: {val}")
                else:
                    resolved[key] = val

        # Layer 3: Explicit config dict (highest priority)
        for key in resolved:
            if key in self.config and self.config[key] not in (None, ""):
                resolved[key] = self.config[key]

        has_explicit_api_key = "api_key" in self.config and self.config.get("api_key") not in (None, "")
        has_explicit_provider = "provider" in self.config and self.config.get("provider") not in (None, "")
        has_explicit_base_url = "base_url" in self.config and self.config.get("base_url") not in (None, "")
        has_explicit_azure_tenant = "azure_tenant_id" in self.config and self.config.get("azure_tenant_id") not in (None, "")
        has_explicit_azure_scope = "azure_scope" in self.config and self.config.get("azure_scope") not in (None, "")

        if has_explicit_base_url and not has_explicit_api_key and not os.environ.get("SOLVITA_API_KEY"):
            resolved["api_key"] = ""

        if (has_explicit_azure_tenant or has_explicit_azure_scope) and not has_explicit_api_key and not os.environ.get("SOLVITA_API_KEY"):
            resolved["provider"] = "openai"
            resolved["api_key"] = ""

        if not resolved["model"]:
            resolved["model"] = "gpt-4"

        if not resolved["provider"]:
            resolved["provider"] = "openai"

        if has_explicit_api_key and not has_explicit_provider:
            resolved["provider"] = "openai"

        provider = str(resolved.get("provider") or "openai").strip().lower()
        if provider in {"openai_compatible", "dashscope", "anthropic"}:
            provider = "openai"
        if provider not in {"openai"}:
            raise self.ConfigurationError(f"Unknown provider: {provider}")
        resolved["provider"] = provider

        if (
            provider == "openai"
            and not resolved["api_key"]
            and resolved["azure_tenant_id"]
            and resolved["azure_scope"]
            and self._looks_like_azure_base_url(resolved["base_url"])
        ):
            self._use_azure = True
        else:
            self._use_azure = False

        if self._use_azure:
            try:
                from azure.identity import AzureCliCredential, get_bearer_token_provider  # noqa: F401
            except ImportError as e:
                raise self.ConfigurationError(
                    "Azure OpenAI AAD auth requires the 'azure-identity' package in the active Python environment"
                ) from e
            if shutil.which("az") is None:
                raise self.ConfigurationError(
                    "Azure OpenAI AAD auth requires the Azure CLI ('az') on PATH and an active az login"
                )

        # Validate required fields
        if not self._use_azure and (not resolved["base_url"] or not resolved["api_key"]):
            raise self.ConfigurationError(
                "LLM configuration incomplete. Provide base_url and api_key (or azure_tenant_id + azure_scope for AAD auth) via one of:\n"
                "  1. config dict passed to UnifiedLLMClient\n"
                "  2. config/models.yaml (llm.base_url / llm.api_key)\n"
                "  3. Environment variables SOLVITA_BASE_URL / SOLVITA_API_KEY"
            )

        if self._use_azure and not resolved["base_url"]:
            raise self.ConfigurationError(
                "Azure OpenAI requires base_url (e.g. https://<azure-endpoint>)"
            )

        return resolved
    def _initialize_client(self):
        """Initialize the OpenAI-compatible HTTP client.

        When api_key is set, prefers the generic OpenAI-compatible client.
        Otherwise, when azure_tenant_id + azure_scope are set, uses AzureOpenAI with
        AAD token provider (AzureCliCredential).
        """
        try:
            if self._use_azure:
                try:
                    from openai import AzureOpenAI
                    from azure.identity import AzureCliCredential, get_bearer_token_provider
                except ImportError as e:
                    raise self.ConfigurationError(
                        "Azure OpenAI AAD auth requires the 'azure-identity' package in the active Python environment"
                    ) from e

                tenant_id = self._resolved["azure_tenant_id"]
                scope = self._resolved["azure_scope"]
                api_version = self._resolved.get("api_version") or "2025-04-01-preview"

                if shutil.which("az") is None:
                    raise self.ConfigurationError(
                        "Azure OpenAI AAD auth requires the Azure CLI ('az') on PATH and an active az login"
                    )

                credential = AzureCliCredential(tenant_id=tenant_id)
                token_provider = get_bearer_token_provider(credential, scope)

                base_url = self.base_url.rstrip("/") + "/"
                if not base_url.endswith("openai/"):
                    base_url = base_url + "openai/"

                logger.info("LLM client: Azure OpenAI (AAD auth) @ {}", base_url)
                return AzureOpenAI(
                    api_version=api_version,
                    base_url=base_url,
                    azure_ad_token_provider=token_provider,
                    max_retries=5,
                )
            else:
                from openai import OpenAI
                logger.info("LLM client: OpenAI-compatible @ {}", self.base_url)
                return OpenAI(base_url=self.base_url, api_key=self.api_key)
        except Exception as e:
            logger.error(f"Error initializing LLM client: {e}")
            raise


    def _record_response_usage(self, response: Any, messages: List[Dict[str, Any]], model: str) -> str:
        content = extract_completion_text(response)
        usage = extract_usage_counts(response)

        prompt_tokens = usage["prompt_tokens"]
        completion_tokens = usage["completion_tokens"]
        prompt_source = "api"
        completion_source = "api"
        if prompt_tokens is None:
            prompt_tokens = estimate_message_tokens(messages, model=model)
            prompt_source = "estimated"
        if completion_tokens is None:
            completion_tokens = estimate_text_tokens(content, model=model)
            completion_source = "estimated"

        if prompt_source == completion_source == "api":
            usage_source = "api"
        elif prompt_source == completion_source == "estimated":
            usage_source = "estimated"
        else:
            usage_source = "mixed"

        record_token_usage(
            self._usage_accumulator,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            source=usage_source,
        )
        self._last_usage = {
            "prompt_tokens": int(prompt_tokens or 0),
            "completion_tokens": int(completion_tokens or 0),
            "token_usage_source": usage_source,
        }
        logger.debug(
            "[LLM Usage] model={} prompt_tokens={} completion_tokens={} source={}",
            model,
            prompt_tokens,
            completion_tokens,
            usage_source,
        )
        return content

    # Models that require max_completion_tokens instead of max_tokens,
    # and do not accept the temperature parameter.
    _REASONING_MODEL_PREFIXES = ("o1", "o3", "o4", "gpt-5")

    @classmethod
    def _is_reasoning_model(cls, model: str) -> bool:
        m = model.lower()
        return any(m.startswith(p) for p in cls._REASONING_MODEL_PREFIXES)

    def _create_chat_completion(self, messages: List[Dict[str, Any]], **kwargs) -> str:
        if not self.client:
            return ""

        model = kwargs.get("model", self.model)
        timeout = kwargs.get("timeout", self.request_timeout)

        reasoning = self._is_reasoning_model(model)

        request_kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "timeout": timeout,
        }

        # Reasoning models use max_completion_tokens and do not accept temperature
        max_tok = kwargs.get("max_tokens", self.max_tokens)
        if reasoning:
            request_kwargs["max_completion_tokens"] = max_tok
        else:
            request_kwargs["max_tokens"] = max_tok
            request_kwargs["temperature"] = kwargs.get("temperature", self.temperature)
        passthrough_keys = (
            "response_format",
            "seed",
            "top_p",
            "frequency_penalty",
            "presence_penalty",
            "stop",
            "logit_bias",
            "n",
            "tools",
            "tool_choice",
            "parallel_tool_calls",
        )
        for key in passthrough_keys:
            if key in kwargs and kwargs[key] is not None:
                request_kwargs[key] = kwargs[key]
        try:
            response = self.client.chat.completions.create(**request_kwargs)
            if isinstance(response, str):
                content = response
                prompt_tokens = estimate_message_tokens(messages, model=model)
                completion_tokens = estimate_text_tokens(content, model=model)
                record_token_usage(
                    self._usage_accumulator,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    source="estimated",
                )
                self._last_usage = {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "token_usage_source": "estimated",
                }
                logger.debug(
                    "[LLM Usage] model={} prompt_tokens={} completion_tokens={} source=estimated",
                    model,
                    prompt_tokens,
                    completion_tokens,
                )
                return content
            return self._record_response_usage(response, messages, model)
        except Exception as e:
            _check_and_raise_prompt_too_long(e)
            _check_and_raise_fatal(e)
            logger.error(f"LLM API error: {e}")
            return ""

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate response from a single prompt."""
        return self._create_chat_completion(
            [{"role": "user", "content": prompt}],
            **kwargs,
        )
    
    def generate_with_system(self, system: str, user: str, **kwargs) -> str:
        """Generate response with system and user messages."""
        return self._create_chat_completion(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            **kwargs,
        )
    
    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """Generate response from chat message history."""
        return self._create_chat_completion(messages, **kwargs)
    
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
        if "request_timeout" in config:
            self.request_timeout = config["request_timeout"]
        if "base_url" in config or "api_key" in config:
            self.client = self._initialize_client()

    @property
    def current_model(self) -> str:
        return self.model

    def get_last_usage(self) -> Dict[str, Any]:
        return dict(self._last_usage)

    def get_usage_snapshot(self) -> Dict[str, Any]:
        return get_token_usage_snapshot(self._usage_accumulator)
    
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
