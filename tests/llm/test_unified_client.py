from src.llm.unified_client import UnifiedLLMClient
import pytest


def test_generate_passes_request_timeout_to_chat_completion(monkeypatch):
    captured = {}

    class DummyCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return "ok"

    class DummyChat:
        def __init__(self):
            self.completions = DummyCompletions()

    class DummyClient:
        def __init__(self):
            self.chat = DummyChat()

    monkeypatch.setattr(UnifiedLLMClient, "_initialize_client", lambda self: DummyClient())

    client = UnifiedLLMClient(
        {
            "base_url": "http://example.test/v1",
            "api_key": "token",
            "model": "demo-model",
            "request_timeout": 17,
        }
    )

    assert client.generate("hello") == "ok"
    assert captured["timeout"] == 17


def test_api_key_mode_overrides_azure_aad(monkeypatch):
    class DummyOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr("openai.OpenAI", DummyOpenAI)

    client = UnifiedLLMClient(
        {
            "base_url": "https://app.ppapi.ai/v1",
            "api_key": "secret",
            "azure_tenant_id": "tenant",
            "azure_scope": "scope",
            "model": "gpt-4o-mini",
        }
    )

    assert client._use_azure is False


def test_env_model_override_skips_yaml_role_model(monkeypatch):
    class DummyOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setenv("SOLVITA_BASE_URL", "https://app.ppapi.ai/v1")
    monkeypatch.setenv("SOLVITA_API_KEY", "secret")
    monkeypatch.setenv("SOLVITA_MODEL", "gpt-4o-mini")
    monkeypatch.setattr("openai.OpenAI", DummyOpenAI)
    monkeypatch.setattr(
        UnifiedLLMClient,
        "_load_yaml_root",
        classmethod(
            lambda cls, config: {
                "llm": {
                    "model": "gpt-4o-mini-2024-07-18",
                    "roles": {"generator": {"model": "gpt-4o-mini-2024-07-18"}},
                }
            }
        ),
    )

    role_cfg = UnifiedLLMClient.build_role_config({}, "generator")
    client = UnifiedLLMClient(role_cfg)

    assert client.current_model == "gpt-4o-mini"
    assert client._use_azure is False


def test_provider_env_aliases_both_supported(monkeypatch):
    class DummyOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr("openai.OpenAI", DummyOpenAI)
    monkeypatch.setenv("SOLVITA_BASE_URL", "https://app.ppapi.ai/v1")
    monkeypatch.setenv("SOLVITA_API_KEY", "secret")
    monkeypatch.setenv("SOLVITA_PROVIDER", "openai_compatible")

    client = UnifiedLLMClient({"model": "gpt-4o-mini"})
    assert client.provider == "openai"

    monkeypatch.delenv("SOLVITA_PROVIDER")
    monkeypatch.setenv("SOLVITA_LLM_PROVIDER", "openai_compatible")
    client = UnifiedLLMClient({"model": "gpt-4o-mini"})
    assert client.provider == "openai"


def test_unknown_provider_fails_fast(monkeypatch):
    monkeypatch.setenv("SOLVITA_BASE_URL", "https://app.ppapi.ai/v1")
    monkeypatch.setenv("SOLVITA_API_KEY", "secret")
    with pytest.raises(UnifiedLLMClient.ConfigurationError):
        UnifiedLLMClient({"model": "gpt-4o-mini", "provider": "unknown-provider"})

