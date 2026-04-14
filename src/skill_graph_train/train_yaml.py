"""
Load ``config/train.yaml`` and merge with CLI for ``scripts/train.py``.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


def load_train_yaml(path: Path) -> Dict[str, Any]:
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


def _pick_num(cli_val: Any, yaml_val: Any, fallback: Any, cast):
    if cli_val is not None:
        return cast(cli_val)
    if yaml_val is not None:
        return cast(yaml_val)
    return cast(fallback)


@dataclass
class ResolvedTrainConfig:
    graph_dir: str
    dataset: str
    solvita_config: Optional[str]
    state_dir: Optional[str]
    epochs: int
    lr: float
    seed: int
    parallel_problems: int
    sample_k: int
    temperature: float
    top_k_problems: int
    contrastive_llm: bool
    max_iterations: int
    solvita_temperature: float
    max_hack_rounds: int
    checkpoint_every: int
    resume: bool
    use_llm_skill_selection: bool
    skill_candidate_k: int
    min_llm_skills: int
    max_llm_skills: int
    max_codegen_attempts: int
    skill_graph_evolution: bool


def resolve_train_config(args: argparse.Namespace, y: Dict[str, Any]) -> ResolvedTrainConfig:
    paths = _sec(y, "paths")
    training = _sec(y, "training")
    rollout = _sec(y, "graph_rollout")
    skill = _sec(y, "skill_selection")
    codegen = _sec(y, "codegen")
    solvita = _sec(y, "solvita_state")
    ckpt = _sec(y, "checkpoint")
    evo = _sec(y, "skill_graph_evolution")

    graph_dir = _pick_str(args.graph_dir, paths.get("graph_dir"), None)
    dataset = _pick_str(args.dataset, paths.get("dataset"), None)
    solvita_raw = _pick_str(args.config, paths.get("solvita_config"), None)
    solvita_config = solvita_raw if solvita_raw else None
    sd = paths.get("state_dir")
    state_dir = _pick_str(args.state_dir, sd, None)
    if state_dir is not None and not str(state_dir).strip():
        state_dir = None

    epochs = _pick_num(args.epochs, training.get("epochs"), 1, int)
    lr = _pick_num(args.lr, training.get("lr"), 0.05, float)
    seed = _pick_num(args.seed, training.get("seed"), 42, int)
    parallel_problems = max(1, _pick_num(args.parallel_problems, training.get("parallel_problems"), 1, int))

    sample_k = _pick_num(args.sample_k, rollout.get("sample_k"), 5, int)
    temperature = _pick_num(args.temperature, rollout.get("temperature"), 1.0, float)
    top_k_problems = _pick_num(args.top_k_problems, rollout.get("top_k_problems"), 5, int)

    contrastive_yaml = bool(codegen.get("contrastive", True))
    contrastive_llm = contrastive_yaml and not args.no_contrastive_codegen

    max_iterations = _pick_num(args.max_iterations, solvita.get("max_iterations"), 1, int)
    solvita_temperature = float(solvita.get("temperature", 0.1))
    max_hack_rounds = int(solvita.get("max_hack_rounds", 0))

    checkpoint_every = _pick_num(args.checkpoint_every, ckpt.get("checkpoint_every"), 50, int)
    resume_yaml = bool(ckpt.get("resume", True))
    resume = resume_yaml and not args.no_resume

    use_llm_yaml = bool(skill.get("use_llm", True))
    use_llm_skill_selection = use_llm_yaml and not args.no_llm_skill_selection

    skill_candidate_k = _pick_num(args.skill_candidate_k, skill.get("candidate_k"), 64, int)
    min_llm_skills = _pick_num(args.min_llm_skills, skill.get("min_llm_skills"), 3, int)
    max_llm_skills = _pick_num(args.max_llm_skills, skill.get("max_llm_skills"), 5, int)
    max_codegen_attempts = _pick_num(args.max_codegen_attempts, codegen.get("max_attempts"), 5, int)

    evo_yaml = bool(evo.get("enabled", True))
    skill_graph_evolution = evo_yaml and not args.no_skill_graph_evolution

    return ResolvedTrainConfig(
        graph_dir=str(graph_dir or ""),
        dataset=str(dataset or ""),
        solvita_config=solvita_config,
        state_dir=str(state_dir).strip() if state_dir else None,
        epochs=epochs,
        lr=lr,
        seed=seed,
        parallel_problems=parallel_problems,
        sample_k=sample_k,
        temperature=temperature,
        top_k_problems=top_k_problems,
        contrastive_llm=contrastive_llm,
        max_iterations=max_iterations,
        solvita_temperature=solvita_temperature,
        max_hack_rounds=max_hack_rounds,
        checkpoint_every=checkpoint_every,
        resume=resume,
        use_llm_skill_selection=use_llm_skill_selection,
        skill_candidate_k=skill_candidate_k,
        min_llm_skills=min_llm_skills,
        max_llm_skills=max_llm_skills,
        max_codegen_attempts=max_codegen_attempts,
        skill_graph_evolution=skill_graph_evolution,
    )
