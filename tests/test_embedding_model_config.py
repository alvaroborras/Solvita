import importlib
import os
import sys
from pathlib import Path


def _reload_qs():
    mod_name = "skill_graph.question_similarity"
    if mod_name in sys.modules:
        return importlib.reload(sys.modules[mod_name])
    return importlib.import_module(mod_name)


def test_embedding_model_from_models_yaml(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("SOLVITA_EMBEDDING_MODEL", raising=False)
    monkeypatch.delenv("SOLVITA_EMBEDDING_PROVIDER", raising=False)
    monkeypatch.setenv("SOLVITA_CONFIG_PATH", str(tmp_path))
    qs = _reload_qs()
    assert qs.resolve_embedding_model() == "text-embedding-3-small"
    cfg = qs.resolve_embedding_config()
    assert cfg.provider == "azure_openai"
    # When the configured base_url is empty (open-source default), the
    # resolved value is the literal empty string rather than a URL.
    assert isinstance(cfg.azure_base_url, str)


def test_embedding_model_env_overrides_yaml(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SOLVITA_CONFIG_PATH", str(tmp_path))
    monkeypatch.setenv("SOLVITA_EMBEDDING_MODEL", "text-embedding-3-large")
    monkeypatch.setenv("SOLVITA_EMBEDDING_PROVIDER", "sentence_transformers")
    qs = _reload_qs()
    assert qs.resolve_embedding_model() == "text-embedding-3-large"
    assert qs.resolve_embedding_config().provider == "sentence_transformers"


def test_embedding_model_default_when_no_config(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("SOLVITA_EMBEDDING_MODEL", raising=False)
    monkeypatch.delenv("SOLVITA_EMBEDDING_PROVIDER", raising=False)
    monkeypatch.setenv("SOLVITA_CONFIG_PATH", str(tmp_path))
    qs = _reload_qs()
    assert qs.resolve_embedding_model() == "text-embedding-3-small"
    assert qs.resolve_embedding_config().provider == "azure_openai"


def test_openai_compatible_config_from_yaml(monkeypatch, tmp_path: Path):
    (tmp_path / "models.yaml").write_text(
        """
embedding:
  provider: openai_compatible
  model: text-embedding-3-small
  http_max_retries: 2
  openai_compatible:
    base_url: https://example.com/api
    api_key: secret-key
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("SOLVITA_CONFIG_PATH", str(tmp_path))
    qs = _reload_qs()
    cfg = qs.resolve_embedding_config()
    assert cfg.provider == "openai_compatible"
    assert cfg.openapi_base_url == "https://example.com/api"
    assert cfg.openapi_api_key == "secret-key"
    assert cfg.http_max_retries == 2


def test_openai_provider_alias_maps_to_openai_compatible(monkeypatch, tmp_path: Path):
    (tmp_path / "models.yaml").write_text(
        """
embedding:
  provider: openai
  model: text-embedding-3-small
  openai_compatible:
    base_url: https://example.com
    api_key: k
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("SOLVITA_CONFIG_PATH", str(tmp_path))
    qs = _reload_qs()
    assert qs.resolve_embedding_config().provider == "openai_compatible"


def test_http_max_retries_env_override(monkeypatch, tmp_path: Path):
    (tmp_path / "models.yaml").write_text(
        """
embedding:
  provider: azure_openai
  model: text-embedding-3-small
  http_max_retries: 1
  azure:
    base_url: https://example.openai.azure.com
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("SOLVITA_CONFIG_PATH", str(tmp_path))
    monkeypatch.setenv("SOLVITA_EMBEDDING_HTTP_MAX_RETRIES", "9")
    qs = _reload_qs()
    assert qs.resolve_embedding_config().http_max_retries == 9
