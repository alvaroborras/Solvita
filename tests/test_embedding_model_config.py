import importlib
import os
import sys
from pathlib import Path


def _reload_qs():
    mod_name = "skill_graph.question_similarity"
    if mod_name in sys.modules:
        return importlib.reload(sys.modules[mod_name])
    return importlib.import_module(mod_name)


def test_embedding_model_from_models_yaml(monkeypatch):
    monkeypatch.delenv("SOLVITA_EMBEDDING_MODEL", raising=False)
    monkeypatch.delenv("SOLVITA_EMBEDDING_PROVIDER", raising=False)
    monkeypatch.setenv("SOLVITA_CONFIG_PATH", "<workspace>/forcel/solvita/config")
    qs = _reload_qs()
    assert qs.resolve_embedding_model() == "text-embedding-3-small"
    cfg = qs.resolve_embedding_config()
    assert cfg.provider == "azure_openai"
    assert cfg.azure_base_url.startswith("https://")


def test_embedding_model_env_overrides_yaml(monkeypatch):
    monkeypatch.setenv("SOLVITA_CONFIG_PATH", "<workspace>/forcel/solvita/config")
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
