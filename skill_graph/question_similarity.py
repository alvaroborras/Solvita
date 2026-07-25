"""
Question similarity Sim(q_new, q_i) for retrieving relevant Q-nodes.

Semantic similarity for problem text uses a configured embedding backend
(Azure OpenAI AAD, OpenAI-compatible HTTP ``/v1/embeddings``, or local
``sentence_transformers``), with a thread-safe LRU cache to avoid redundant API calls.

加权和
-------
Sim = problem_semantic_weight · Sim_problem + tag_jaccard_weight · Jaccard(tags)（权重和为 1）。

1. **Sim_problem**（训练管线）：``similarity_description`` = canonical_problem 文本，空则 **原题 description**；
   与 Q 的 **``abstract_description``** 算余弦。字段为 ``None`` 时回退 ``description + direction``。
2. **Jaccard(tags)**：``similarity_tags`` = planner ``algorithmic_tags``，空则 **数据行 tags**（与 ``PlannerInput.tags`` 同源）。
   图节点侧：**``q.tags``**，若为空则用 **``tags_level1``**。

环境变量
--------
- ``SOLVITA_EMBEDDING_MODEL``：OpenAI embedding 模型名（默认 ``text-embedding-3-small``）。
- ``SOLVITA_EMBEDDING_OPENAI_BASE_URL``：当 ``provider: openai_compatible`` 时覆盖
  ``embedding.openai_compatible.base_url``。认证由 OpenAI SDK 从 ``OPENAI_API_KEY`` 读取。
- ``SOLVITA_EMBEDDING_HTTP_MAX_RETRIES``：覆盖 ``embedding.http_max_retries``（HTTP 嵌入客户端，默认 5）。

MS 边初始化复用同一模型与同一套「标签句 + 逻辑文本」余弦思路，见
``ms_init_*`` / ``encode_l2_normalized_batch``。
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, List

import numpy as np
import yaml

from .blocks import FunctionBlock
from .nodes import QNode, SNode
from .tag_utils import canonicalize_tag_set, jaccard_similarity_tags

if TYPE_CHECKING:
    from .inference import PlannerInput

# ---------------------------------------------------------------------------
# Embedding backend config and lazy clients
# ---------------------------------------------------------------------------
_EMB_CLIENT = None
_ST_MODEL = None
_EMB_LOCK = threading.Lock()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _models_yaml_path() -> Path:
    config_root = os.environ.get("SOLVITA_CONFIG_PATH", "")
    if config_root:
        p = Path(config_root).expanduser().resolve()
        return p / "models.yaml"
    return _repo_root() / "config" / "models.yaml"


def _embedding_section_from_models_yaml() -> dict[str, Any]:
    path = _models_yaml_path()
    if not path.is_file():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return {}
    emb = data.get("embedding")
    return emb if isinstance(emb, dict) else {}


@dataclass(frozen=True)
class EmbeddingConfig:
    provider: str
    model: str
    cache_size: int
    http_max_retries: int
    azure_base_url: str
    azure_tenant_id: str
    azure_scope: str
    azure_api_version: str
    st_device: str
    openapi_base_url: str = ""


def resolve_embedding_config() -> EmbeddingConfig:
    """Resolve embedding backend configuration from env vars and models.yaml."""
    emb = _embedding_section_from_models_yaml()

    provider = str(
        os.environ.get("SOLVITA_EMBEDDING_PROVIDER")
        or emb.get("provider")
        or "azure_openai"
    ).strip().lower()
    if provider == "openai":
        provider = "openai_compatible"

    model = str(
        os.environ.get("SOLVITA_EMBEDDING_MODEL")
        or emb.get("model")
        or "text-embedding-3-small"
    ).strip()

    cache_size_raw = (
        os.environ.get("SOLVITA_EMBEDDING_CACHE_SIZE")
        or emb.get("cache_size")
        or 32768
    )
    try:
        cache_size = max(1024, int(cache_size_raw))
    except (TypeError, ValueError):
        cache_size = 32768

    emb_http = emb.get("http") if isinstance(emb.get("http"), dict) else {}
    http_retries_raw = (
        os.environ.get("SOLVITA_EMBEDDING_HTTP_MAX_RETRIES")
        or emb.get("http_max_retries")
        or emb_http.get("max_retries")
        or 5
    )
    try:
        http_max_retries = max(0, int(http_retries_raw))
    except (TypeError, ValueError):
        http_max_retries = 5

    oc = emb.get("openai_compatible") if isinstance(emb.get("openai_compatible"), dict) else {}
    openapi_base_url = str(
        os.environ.get("SOLVITA_EMBEDDING_OPENAI_BASE_URL") or oc.get("base_url") or ""
    ).strip()
    azure = emb.get("azure") if isinstance(emb.get("azure"), dict) else {}
    azure_base_url = str(
        os.environ.get("SOLVITA_EMBEDDING_AZURE_BASE_URL")
        or os.environ.get("SOLVITA_BASE_URL")
        or azure.get("base_url")
        or ""
    ).strip()
    azure_tenant_id = str(
        os.environ.get("SOLVITA_EMBEDDING_AZURE_TENANT_ID")
        or azure.get("tenant_id")
        or ""
    ).strip()
    azure_scope = str(
        os.environ.get("SOLVITA_EMBEDDING_AZURE_SCOPE")
        or azure.get("scope")
        or "<your-azure-scope-uri>"
    ).strip()
    azure_api_version = str(
        os.environ.get("SOLVITA_EMBEDDING_AZURE_API_VERSION")
        or azure.get("api_version")
        or "2025-04-01-preview"
    ).strip()

    st = (
        emb.get("sentence_transformers")
        if isinstance(emb.get("sentence_transformers"), dict)
        else {}
    )
    st_device = str(
        os.environ.get("SOLVITA_ST_DEVICE")
        or st.get("device")
        or "cpu"
    ).strip()

    return EmbeddingConfig(
        provider=provider,
        model=model,
        cache_size=cache_size,
        http_max_retries=http_max_retries,
        azure_base_url=azure_base_url,
        azure_tenant_id=azure_tenant_id,
        azure_scope=azure_scope,
        azure_api_version=azure_api_version,
        st_device=st_device,
        openapi_base_url=openapi_base_url,
    )


def resolve_embedding_model() -> str:
    """Backward-compatible helper: return resolved embedding model name."""
    return resolve_embedding_config().model


_EMB_CONFIG = resolve_embedding_config()
_EMB_MODEL = _EMB_CONFIG.model
_EMB_CACHE_SIZE = _EMB_CONFIG.cache_size


def _normalize_openai_compatible_base_url(base_url: str) -> str:
    """Ensure base_url is suitable for ``openai.OpenAI`` (…/v1 suffix)."""
    s = (base_url or "").strip().rstrip("/")
    if not s:
        return ""
    if s.endswith("/v1"):
        return s
    return f"{s}/v1"


def _get_embedding_client():
    """Return a shared HTTP embedding client (Azure OpenAI AAD or OpenAI-compatible)."""
    global _EMB_CLIENT
    if _EMB_CLIENT is not None:
        return _EMB_CLIENT
    with _EMB_LOCK:
        if _EMB_CLIENT is not None:
            return _EMB_CLIENT
        import openai

        retries = int(getattr(_EMB_CONFIG, "http_max_retries", 5) or 5)

        if _EMB_CONFIG.provider == "azure_openai":
            from azure.identity import AzureCliCredential, get_bearer_token_provider

            credential = AzureCliCredential(tenant_id=_EMB_CONFIG.azure_tenant_id)
            token_provider = get_bearer_token_provider(credential, _EMB_CONFIG.azure_scope)

            base_url = _EMB_CONFIG.azure_base_url.rstrip("/") + "/"
            if not base_url.endswith("openai/"):
                base_url = base_url + "openai/"

            _EMB_CLIENT = openai.AzureOpenAI(
                api_version=_EMB_CONFIG.azure_api_version,
                base_url=base_url,
                azure_ad_token_provider=token_provider,
                max_retries=retries,
            )
            return _EMB_CLIENT

        if _EMB_CONFIG.provider == "openai_compatible":
            bu = _normalize_openai_compatible_base_url(_EMB_CONFIG.openapi_base_url)
            if not bu:
                raise RuntimeError(
                    "embedding.provider is 'openai_compatible' but base_url is missing. "
                    "Set embedding.openai_compatible.base_url or "
                    "SOLVITA_EMBEDDING_OPENAI_BASE_URL. Authentication is read from OPENAI_API_KEY."
                )
            _EMB_CLIENT = openai.OpenAI(
                base_url=bu,
                max_retries=retries,
            )
            return _EMB_CLIENT

        raise RuntimeError(
            f"embedding.provider {_EMB_CONFIG.provider!r} does not use the HTTP embedding client"
        )


def _embeddings_create_with_retry(client, *, input, max_attempts: int = 8, base_sleep: float = 2.0):
    """Wrap ``client.embeddings.create`` with additional retry on 429/5xx.

    The SDK already retries internally but bursty parallel workers can exhaust
    its budget; this wrapper layers an extra exponential backoff on top so a
    sustained quota squeeze does not surface as a hard workflow failure.
    """
    import time
    import random

    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return client.embeddings.create(model=_EMB_MODEL, input=input)
        except Exception as exc:  # openai.RateLimitError, APIError, etc.
            msg = str(exc)
            is_429 = "429" in msg or "RateLimit" in msg or "rate limit" in msg.lower()
            is_5xx = any(code in msg for code in ("500", "502", "503", "504"))
            if not (is_429 or is_5xx):
                raise
            last_exc = exc
            if attempt == max_attempts - 1:
                break
            sleep_s = base_sleep * (2 ** attempt) + random.uniform(0.0, 1.0)
            sleep_s = min(sleep_s, 60.0)
            time.sleep(sleep_s)
    assert last_exc is not None
    raise last_exc


def _get_sentence_transformer_model():
    """Return a shared SentenceTransformer model."""
    global _ST_MODEL
    if _ST_MODEL is not None:
        return _ST_MODEL
    with _EMB_LOCK:
        if _ST_MODEL is not None:
            return _ST_MODEL
        try:
            from sentence_transformers import SentenceTransformer
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "sentence-transformers backend requested, but package is not installed. "
                "Install with: pip install sentence-transformers"
            ) from exc
        _ST_MODEL = SentenceTransformer(_EMB_MODEL, device=_EMB_CONFIG.st_device)
        return _ST_MODEL


# ---------------------------------------------------------------------------
# Embedding cache (dict-based, thread-safe, allows batch pre-population)
# ---------------------------------------------------------------------------
_EMB_CACHE: dict[str, np.ndarray] = {}
_EMB_CACHE_LOCK = threading.Lock()


def _embed_text(text: str) -> np.ndarray:
    """Embed a single text string with the configured backend; results are dict-cached."""
    if text in _EMB_CACHE:
        return _EMB_CACHE[text]
    if _EMB_CONFIG.provider == "sentence_transformers":
        model = _get_sentence_transformer_model()
        vec = np.asarray(
            model.encode([text], convert_to_numpy=True, normalize_embeddings=False)[0],
            dtype=np.float64,
        )
    elif _EMB_CONFIG.provider in ("azure_openai", "openai_compatible"):
        client = _get_embedding_client()
        resp = _embeddings_create_with_retry(client, input=text)
        vec = np.asarray(resp.data[0].embedding, dtype=np.float64)
    else:
        raise ValueError(
            f"Unsupported embedding provider: {_EMB_CONFIG.provider!r}. "
            "Use 'azure_openai', 'openai_compatible', or 'sentence_transformers'."
        )
    with _EMB_CACHE_LOCK:
        _EMB_CACHE[text] = vec
    return vec


def warmup_embedding_cache(texts: List[str], batch_size: int = 256) -> int:
    """Batch-embed texts and populate the cache upfront. Returns count of new embeddings."""
    unique_texts = list({(t or "").strip() for t in texts if (t or "").strip()})
    to_embed = [t for t in unique_texts if t not in _EMB_CACHE]
    if not to_embed:
        return 0
    embedded = 0
    if _EMB_CONFIG.provider == "sentence_transformers":
        model = _get_sentence_transformer_model()
        for i in range(0, len(to_embed), batch_size):
            batch = to_embed[i : i + batch_size]
            embs = model.encode(
                batch,
                convert_to_numpy=True,
                normalize_embeddings=False,
                batch_size=max(8, int(batch_size)),
            )
            with _EMB_CACHE_LOCK:
                for j, txt in enumerate(batch):
                    _EMB_CACHE[txt] = np.asarray(embs[j], dtype=np.float64)
                    embedded += 1
        return embedded

    if _EMB_CONFIG.provider not in ("azure_openai", "openai_compatible"):
        raise ValueError(
            f"Unsupported embedding provider: {_EMB_CONFIG.provider!r}. "
            "Use 'azure_openai', 'openai_compatible', or 'sentence_transformers'."
        )

    client = _get_embedding_client()
    for i in range(0, len(to_embed), batch_size):
        batch = to_embed[i : i + batch_size]
        resp = _embeddings_create_with_retry(client, input=batch)
        with _EMB_CACHE_LOCK:
            for d in sorted(resp.data, key=lambda x: x.index):
                _EMB_CACHE[batch[d.index]] = np.asarray(d.embedding, dtype=np.float64)
                embedded += 1
    return embedded


def _cosine_dense(va: np.ndarray, vb: np.ndarray) -> float:
    na, nb = float(np.linalg.norm(va)), float(np.linalg.norm(vb))
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    c = float(np.dot(va, vb) / (na * nb))
    return max(0.0, min(1.0, c))


def _embedding_cosine_pair(text_a: str, text_b: str, *, both_empty: float) -> float:
    """Encode two strings with OpenAI embedding API; return cosine similarity in [0, 1]."""
    a = (text_a or "").strip()
    b = (text_b or "").strip()
    if not a and not b:
        return both_empty
    if not a or not b:
        return 0.0
    va = _embed_text(a)
    vb = _embed_text(b)
    return _cosine_dense(va, vb)


def problem_text_similarity(query_text: str, doc_text: str) -> float:
    """题干相似度：两句文本的句向量余弦。"""
    return _embedding_cosine_pair(query_text, doc_text, both_empty=0.0)


def tag_semantic_similarity(tags_a: Iterable[str], tags_b: Iterable[str]) -> float:
    """标签语义相似度：拼接 canonical 标签后的两句文本的句向量余弦。"""
    sa = " ".join(sorted(canonicalize_tag_set(tags_a)))
    sb = " ".join(sorted(canonicalize_tag_set(tags_b)))
    return _embedding_cosine_pair(sa, sb, both_empty=0.0)


# ---------------------------------------------------------------------------
# MS 边初始化：与 Sim 一致的「标签句 + 逻辑文本」通道（供 EdgeWeightInitializer 批量编码）
# ---------------------------------------------------------------------------

def ms_init_block_tag_string(block: FunctionBlock) -> str:
    s = " ".join(sorted(canonicalize_tag_set(block.tags)))
    return s if s else "[no_tags]"


def ms_init_skill_tag_string(skill: SNode) -> str:
    s = " ".join(sorted(canonicalize_tag_set(skill.tags)))
    return s if s else "[no_tags]"


def ms_init_block_logic_text(block: FunctionBlock, max_code_chars: int = 3000) -> str:
    """FunctionBlock 侧「逻辑」文本：名称/标签 + role + 截断 code。"""
    code = (block.code or "")[: max(0, max_code_chars)]
    parts = [block.name_or_label or "", block.role or "", code]
    return "\n".join(p for p in parts if p).strip() or "[no_logic]"


def ms_init_skill_logic_text(skill: SNode, max_code_chars: int = 3000) -> str:
    """S 节点侧「逻辑」文本：标题 + 描述 + 截断模板代码。"""
    ct = (skill.code_template or "")[: max(0, max_code_chars)]
    parts = [skill.title or "", skill.description or "", ct]
    return "\n".join(p for p in parts if p).strip() or "[no_logic]"


def encode_l2_normalized_batch(
    texts: List[str],
    *,
    batch_size: int = 64,
) -> np.ndarray:
    """
    Batch-encode text embeddings and L2-normalize rows using configured backend.

    空串会替换为 ``[empty]``，避免无效输入。
    """
    if not texts:
        return np.zeros((0, 0), dtype=np.float64)
    safe = [t if (t or "").strip() else "[empty]" for t in texts]
    bs = int(os.environ.get("SOLVITA_ST_ENCODE_BATCH", str(batch_size)))
    all_embs = []
    eff_bs = max(8, bs)
    if _EMB_CONFIG.provider == "sentence_transformers":
        model = _get_sentence_transformer_model()
        for i in range(0, len(safe), eff_bs):
            batch = safe[i : i + eff_bs]
            embs = model.encode(
                batch,
                convert_to_numpy=True,
                normalize_embeddings=False,
                batch_size=eff_bs,
            )
            for row in embs:
                all_embs.append(row)
    elif _EMB_CONFIG.provider in ("azure_openai", "openai_compatible"):
        client = _get_embedding_client()
        for i in range(0, len(safe), eff_bs):
            batch = safe[i : i + eff_bs]
            resp = _embeddings_create_with_retry(client, input=batch)
            for d in sorted(resp.data, key=lambda x: x.index):
                all_embs.append(d.embedding)
    else:
        raise ValueError(
            f"Unsupported embedding provider: {_EMB_CONFIG.provider!r}. "
            "Use 'azure_openai', 'openai_compatible', or 'sentence_transformers'."
        )
    arr = np.asarray(all_embs, dtype=np.float64)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-12)
    return arr / norms


def block_skill_ms_init_similarity(
    block: FunctionBlock,
    skill: SNode,
    *,
    tag_weight: float = 0.5,
    logic_weight: float = 0.5,
    max_code_chars: int = 3000,
) -> float:
    """
    单对 (FunctionBlock, SNode) 的 MS 初始化分数，与检索 Sim 同构：
    tag_weight·cos(E(tags), E(tags')) + logic_weight·cos(E(logic), E(logic'))，分量夹紧到 [0,1]。
    """
    s_tag = tag_semantic_similarity(block.tags, skill.tags)
    s_log = problem_text_similarity(
        ms_init_block_logic_text(block, max_code_chars),
        ms_init_skill_logic_text(skill, max_code_chars),
    )
    return tag_weight * s_tag + logic_weight * s_log


@dataclass(frozen=True)
class QuestionSimilarityWeights:
    """
    Sim(q_new, q_i) = problem_semantic_weight * Sim_problem
                    + tag_jaccard_weight * Jaccard(tags).

    Sim_problem: sentence-embedding cosine between query text and Q.abstract_description.
    Jaccard: on canonicalised tag sets (see :func:`jaccard_similarity_tags`).
    Weights must sum to 1.0.
    """

    problem_semantic_weight: float = 0.5
    tag_jaccard_weight: float = 0.5

    def __post_init__(self) -> None:
        s = self.problem_semantic_weight + self.tag_jaccard_weight
        if abs(s - 1.0) > 1e-6:
            raise ValueError(
                "problem_semantic_weight + tag_jaccard_weight must equal 1.0"
            )


def sim_planner_to_qnode(
    planner: "PlannerInput",
    q: QNode,
    weights: QuestionSimilarityWeights | None = None,
) -> float:
    """
    Sim(q_new, q_i) = w_prob · cos_emb(text_left, q_i.abstract_description)
                    + w_tag · Jaccard(tags_left, q_i.tags_or_level1).

    - 语义左侧：``similarity_description`` = canonical_problem 或（空时）**原题 description**；
      若为 ``None``，回退 ``description + direction``。
    - 标签左侧：``similarity_tags`` = algorithmic_tags 或（空时）**数据集 tags**；
      若为 ``None``，回退 ``planner.tags``。
    - 图节点：``q.tags`` 非空则用其，否则 **tags_level1**。
    """
    w = weights or QuestionSimilarityWeights()
    sim_desc = getattr(planner, "similarity_description", None)
    if sim_desc is not None:
        query_text = str(sim_desc).strip()
    else:
        query_text = (planner.description or "") + "\n" + (planner.direction or "")
    doc_text = (getattr(q, "abstract_description", None) or "")

    s_prob = problem_text_similarity(query_text, doc_text)
    q_tag_primary = q.tags if getattr(q, "tags", None) else getattr(q, "tags_level1", None)
    st_tags = getattr(planner, "similarity_tags", None)
    if st_tags is not None:
        planner_tags = list(st_tags)
    else:
        planner_tags = planner.tags
    s_jac = jaccard_similarity_tags(planner_tags, q_tag_primary or [])

    return w.problem_semantic_weight * s_prob + w.tag_jaccard_weight * s_jac
