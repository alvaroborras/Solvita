"""Role prompts and leakage-safe context assembly for heuristic optimization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .knowledge import StrategyCard
from .operators import Operator


@dataclass(frozen=True)
class RolePrompt:
    role: str
    system: str
    user: str


def planner_prompt(
    problem_statement: str, feature_summary: Mapping[str, Any]
) -> RolePrompt:
    return RolePrompt(
        "planner",
        "You are Solvita Planner. Produce optimization analysis, architecture hypotheses, and independent seed briefs. Do not write final code.",
        f"Problem:\n{problem_statement}\n\nTraining feature summary:\n{dict(feature_summary)}",
    )


def solver_prompt(
    *,
    operator: Operator,
    parent_sources: Sequence[str],
    training_feedback: Mapping[str, Any],
    strategies: Sequence[StrategyCard],
) -> RolePrompt:
    strategy_text = (
        "\n".join(
            f"- {card.card_id}: {card.mechanism}; preconditions={list(card.preconditions)}"
            for card in strategies
        )
        or "- none"
    )
    mode = (
        "minimal constrained patch"
        if operator.mode == "patch"
        else "complete bundle rewrite"
    )
    return RolePrompt(
        "solver",
        "You are Solvita Solver. Return only canonical CandidateBundleV1 JSON. Never request or infer validation data, BKS artifacts, or scorer internals.",
        f"Operator: {operator.name}\nMode: {mode}\nInstruction: {operator.instruction}\n"
        f"Training-only feedback: {dict(training_feedback)}\nStrategies:\n{strategy_text}\n"
        f"Parent sources:\n{list(parent_sources)}",
    )


def oracle_prompt(epoch: int, training_diagnostics: Mapping[str, Any]) -> RolePrompt:
    return RolePrompt(
        "oracle",
        "You are Solvita Oracle. Audit scorer versions, pending training BKS, and anomalies. You may not change scorer semantics.",
        f"Epoch: {epoch}\nTraining diagnostics only: {dict(training_diagnostics)}",
    )


def hacker_prompt(epoch: int, training_diagnostics: Mapping[str, Any]) -> RolePrompt:
    return RolePrompt(
        "hacker",
        "You are Solvita Hacker. Analyze regret, rank flips, weak in-distribution clusters, invalidity, and timeouts. OOD cases are diagnostic only.",
        f"Epoch: {epoch}\nTraining diagnostics only: {dict(training_diagnostics)}",
    )


def assert_no_validation_leakage(context: Mapping[str, Any]) -> None:
    forbidden = {
        "validation",
        "validation_objectives",
        "validation_outputs",
        "validation_bks",
        "validation_instances",
        "best_validation_lcb",
    }
    leaked = sorted(forbidden & set(context))
    if leaked:
        raise ValueError(
            f"validation information may not enter agent context: {leaked}"
        )
