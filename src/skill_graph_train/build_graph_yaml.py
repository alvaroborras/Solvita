"""
Load ``config/build_initial_graph.yaml`` and merge with CLI for ``scripts/build_initial_graph.py``.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from skill_graph.initializer import SimilarityMetric


def load_build_graph_yaml(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def _sec(y: Dict[str, Any], key: str) -> Dict[str, Any]:
    v = y.get(key)
    return v if isinstance(v, dict) else {}


def _pick_str(cli_val: Any, yaml_val: Any, fallback: Any) -> Any:
    if cli_val is not None and str(cli_val).strip():
        return str(cli_val).strip()
    if yaml_val is not None and str(yaml_val).strip():
        return str(yaml_val).strip()
    return fallback


def _pick_opt_int(cli_val: Any, yaml_val: Any) -> Optional[int]:
    if cli_val is not None:
        return int(cli_val)
    if yaml_val is None:
        return None
    if isinstance(yaml_val, str) and not yaml_val.strip():
        return None
    return int(yaml_val)


def _pick_int(cli_val: Any, yaml_val: Any, fallback: int) -> int:
    if cli_val is not None:
        return int(cli_val)
    if yaml_val is not None:
        return int(yaml_val)
    return int(fallback)


def _pick_bool(cli_val: Any, yaml_val: Any, fallback: bool) -> bool:
    if cli_val is not None:
        return bool(cli_val)
    if yaml_val is not None:
        return bool(yaml_val)
    return fallback


_METRIC_ALIASES: Dict[str, SimilarityMetric] = {
    "embedding": SimilarityMetric.EMBEDDING,
    "emb": SimilarityMetric.EMBEDDING,
    "jaccard": SimilarityMetric.JACCARD,
    "overlap": SimilarityMetric.OVERLAP,
    "cosine": SimilarityMetric.COSINE,
}


def parse_ms_metric(name: Optional[str]) -> SimilarityMetric:
    if not name:
        return SimilarityMetric.EMBEDDING
    key = str(name).strip().lower()
    return _METRIC_ALIASES.get(key, SimilarityMetric.EMBEDDING)


@dataclass
class ResolvedBuildGraphConfig:
    logic_jsonl: str
    skills_dir: str
    out_dir: str
    q_limit: Optional[int]
    m_limit: Optional[int]
    s_limit: Optional[int]
    top_k_per_block: int
    create_zero_edges: bool
    metric: SimilarityMetric
    sentence_transformer_model: Optional[str]
    # logging (build script): None -> default <out_dir>/build_initial_graph_log.txt
    log_txt: Optional[str]
    loader_progress_every: int
    ms_block_log_step: Optional[int]


def resolve_build_graph_config(args: argparse.Namespace, y: Dict[str, Any]) -> ResolvedBuildGraphConfig:
    paths = _sec(y, "paths")
    limits = _sec(y, "limits")
    ms_init = _sec(y, "ms_init")
    emb = _sec(y, "embedding")
    logg = _sec(y, "logging")

    _root = Path(__file__).resolve().parents[2]
    default_logic = _root / "datasets" / "solvita_logic_train.augmented.jsonl"
    default_skills = _root / "skills"
    default_out = _root / "data" / "initial_graph"

    logic_jsonl = _pick_str(
        getattr(args, "logic_jsonl", None),
        paths.get("logic_jsonl"),
        str(default_logic),
    )
    skills_dir = _pick_str(
        getattr(args, "skills_dir", None),
        paths.get("skills_dir"),
        str(default_skills),
    )
    out_dir = _pick_str(
        getattr(args, "out_dir", None),
        paths.get("out_dir"),
        str(default_out),
    )

    q_limit = _pick_opt_int(getattr(args, "q_limit", None), limits.get("q_limit"))
    m_limit = _pick_opt_int(getattr(args, "m_limit", None), limits.get("m_limit"))
    s_limit = _pick_opt_int(getattr(args, "s_limit", None), limits.get("s_limit"))

    top_k = _pick_int(
        getattr(args, "top_k_per_block", None),
        ms_init.get("top_k_per_block"),
        16,
    )
    if getattr(args, "create_zero_edges", False):
        create_zero = True
    elif getattr(args, "no_create_zero_edges", False):
        create_zero = False
    else:
        create_zero = _pick_bool(None, ms_init.get("create_zero_edges"), False)
    metric = parse_ms_metric(
        getattr(args, "ms_metric", None) or ms_init.get("metric"),
    )

    model = emb.get("sentence_transformer_model")
    if isinstance(model, str) and model.strip():
        st_model: Optional[str] = model.strip()
    else:
        st_model = None

    cli_log = getattr(args, "log_txt", None)
    if cli_log is not None and str(cli_log).strip():
        log_txt: Optional[str] = str(cli_log).strip()
    else:
        lt = logg.get("log_txt")
        if lt is not None and str(lt).strip():
            log_txt = str(lt).strip()
        else:
            log_txt = None

    lpe = _pick_int(
        getattr(args, "loader_progress_every", None),
        logg.get("loader_progress_every"),
        50,
    )
    lpe = max(1, lpe)

    if getattr(args, "ms_block_log_step", None) is not None:
        ms_block_log_step = int(args.ms_block_log_step)
    elif "ms_block_log_step" not in logg:
        ms_block_log_step = None
    else:
        rv = logg["ms_block_log_step"]
        ms_block_log_step = None if rv is None else int(rv)

    return ResolvedBuildGraphConfig(
        logic_jsonl=logic_jsonl,
        skills_dir=skills_dir,
        out_dir=out_dir,
        q_limit=q_limit,
        m_limit=m_limit,
        s_limit=s_limit,
        top_k_per_block=max(1, top_k),
        create_zero_edges=create_zero,
        metric=metric,
        sentence_transformer_model=st_model,
        log_txt=log_txt,
        loader_progress_every=lpe,
        ms_block_log_step=ms_block_log_step,
    )


def apply_embedding_env(rc: ResolvedBuildGraphConfig) -> None:
    """Set SOLVITA_SIM_ST_MODEL before SentenceTransformer is first loaded."""
    if rc.sentence_transformer_model:
        os.environ["SOLVITA_SIM_ST_MODEL"] = rc.sentence_transformer_model
