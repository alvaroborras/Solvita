"""Optimize-anything engine adapters and matched-budget search policies."""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .operators import Operator
from .workflow import HeuristicRunState

try:  # The pinned GEPA OA API is an optional import for local contract tests.
    from gepa.oa.engine import Result
    from gepa.oa.registry import register_engine as _oa_register_engine
    from gepa.oa.task import seed_as_text

    OA_AVAILABLE = True
except ModuleNotFoundError:
    OA_AVAILABLE = False

    @dataclass
    class Result:  # type: ignore[no-redef]
        best_candidate: str
        best_score: float
        total_evals: int = 0
        eval_log: list[dict[str, Any]] | None = None
        metadata: dict[str, Any] | None = None

    _oa_register_engine: Any = None

    def seed_as_text(seed):
        if seed is None:
            return ""
        if isinstance(seed, str):
            return seed
        raise TypeError("solvita_dgs requires a single text candidate")


Proposer = Callable[[str, Operator, Sequence[str], Mapping[str, Any]], str]
OA_ENGINE_MAP = {
    "solvita_dgs": "solvita_dgs",
    "random_qd": "random_qd",
    "best_of_n": "best_of_n",
    "default_gepa": "gepa",
}


def oa_engine_name(public_name: str) -> str:
    try:
        return OA_ENGINE_MAP[public_name]
    except KeyError as exc:
        raise ValueError(f"unknown comparison engine: {public_name}") from exc


class SolvitaDGSEngine:
    """Custom OA engine where Solvita-DGS exclusively owns action selection."""

    name = "solvita_dgs"

    def __init__(self, config):
        values = dict(getattr(config, "engine_config", {}) or {})
        self.proposer: Proposer | None = values.pop("proposer", None)
        self.proposals = int(values.pop("proposals", 200))
        self.support_calls = int(values.pop("support_calls", 40))
        self.seed = int(values.pop("seed", 0))
        self.max_token_cost = getattr(config, "max_token_cost", None)
        self.stop_at_score = getattr(config, "stop_at_score", None)
        self.run_dir = getattr(config, "run_dir", None)
        if values:
            warnings.warn(
                f"unknown solvita_dgs engine keys: {sorted(values)}", stacklevel=2
            )

    def _propose(
        self,
        seed: str,
        operator: Operator,
        parents: Sequence[str],
        context: Mapping[str, Any],
    ) -> str:
        if self.proposer is None:
            # Contract-safe deterministic mode for smoke tests. Production CLI
            # requires a configured Solver and refuses this mode.
            return seed
        return self.proposer(seed, operator, parents, context)

    def run(self, task, server) -> Result:
        seed = seed_as_text(task.seed_candidate)
        state = HeuristicRunState(
            run_id=getattr(task, "name", "solvita"),
            proposal_budget=self.proposals,
            support_budget=self.support_calls,
            rng_seed=self.seed,
        )
        candidates: dict[str, str] = {}
        best_candidate, best_score = seed, float("-inf")
        log: list[dict[str, Any]] = []
        while not state.should_stop():
            operator = state.select_operator(self.name)
            parent_entries = state.select_parents(operator, self.name)
            parent_sources = [
                candidates[e.candidate_hash]
                for e in parent_entries
                if e.candidate_hash in candidates
            ]
            candidate = self._propose(
                seed,
                operator,
                parent_sources,
                {"proposal": state.proposals + 1, "objective": task.objective},
            )
            proposal = state.consume_proposal()  # malformed/duplicate still counts
            score, info = server.evaluate_examples(candidate, split="train")
            candidate_hash = (
                __import__("hashlib").sha256(candidate.encode()).hexdigest()
            )
            candidates[candidate_hash] = candidate
            from .archive import ArchiveEntry

            state.archive.add(
                ArchiveEntry(
                    candidate_hash,
                    float(score),
                    novelty=float(info.get("novelty", 0.0)),
                )
            )
            if score > best_score:
                best_candidate, best_score = candidate, float(score)
            log.append(
                {
                    "proposal": proposal,
                    "operator": operator.name,
                    "candidate_hash": candidate_hash,
                    "score": float(score),
                    "info": info,
                }
            )
            if self.stop_at_score is not None and best_score >= self.stop_at_score:
                break
        return Result(
            best_candidate=best_candidate,
            best_score=best_score,
            total_evals=len(log),
            eval_log=log,
            metadata={"proposals": state.proposals, "engine": self.name},
        )

    def process_result(self, result: Result, output_dir: Path | None) -> None:
        if output_dir is None:
            return
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "solvita_dgs_result.json").write_text(
            json.dumps(
                {
                    "best_candidate": result.best_candidate,
                    "best_score": result.best_score,
                    "total_evals": result.total_evals,
                    "metadata": result.metadata,
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )


class RandomQDEngine(SolvitaDGSEngine):
    """Matched archive/operators with random, rather than surrogate, actions."""

    name = "random_qd"


def register_gepa_engines() -> bool:
    """Register the custom engine when the pinned OA registry is installed."""
    if _oa_register_engine is None:
        return False
    _oa_register_engine("solvita_dgs", SolvitaDGSEngine)
    _oa_register_engine("random_qd", RandomQDEngine)
    return True


def verify_gepa_oa() -> None:
    if not OA_AVAILABLE:
        raise RuntimeError(
            "GEPA OA API is unavailable; install commit "
            "f919db0a622e2e9f9204779b81fe00cc1b2d808f from requirements.txt"
        )


# Importing this module on a compatible GEPA revision is sufficient to expose
# the public engine name.
register_gepa_engines()
