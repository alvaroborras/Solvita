"""Versioned mutation/operator registry used by all QD engines."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Operator:
    name: str
    mode: str
    arity: int
    family: str
    instruction: str


OPERATORS: tuple[Operator, ...] = (
    Operator(
        "tune_parameters",
        "patch",
        1,
        "parameter",
        "Tune numeric parameters and schedules.",
    ),
    Operator(
        "change_acceptance",
        "patch",
        1,
        "acceptance",
        "Revise acceptance and cooling logic.",
    ),
    Operator(
        "add_neighborhood",
        "patch",
        1,
        "neighborhood",
        "Add a targeted local-search neighborhood.",
    ),
    Operator(
        "optimize_hot_path",
        "patch",
        1,
        "performance",
        "Reduce allocations and hot-path complexity.",
    ),
    Operator(
        "add_restart",
        "patch",
        1,
        "restart",
        "Add adaptive restarts and diversification.",
    ),
    Operator(
        "destroy_repair", "rewrite", 1, "lns", "Introduce a destroy-and-repair phase."
    ),
    Operator(
        "change_representation",
        "rewrite",
        1,
        "representation",
        "Change the solution representation.",
    ),
    Operator(
        "new_paradigm",
        "rewrite",
        1,
        "architecture",
        "Replace the search with a different paradigm.",
    ),
    Operator(
        "specialize_cluster",
        "patch",
        1,
        "specialization",
        "Specialize for a weak feature cluster.",
    ),
    Operator(
        "generalize",
        "patch",
        1,
        "generalization",
        "Remove brittle instance-specific assumptions.",
    ),
    Operator(
        "recombine",
        "rewrite",
        2,
        "recombination",
        "Architecturally recombine complementary parents.",
    ),
    Operator(
        "repair_invalid",
        "patch",
        1,
        "repair",
        "Repair compilation, parsing, timeout, or feasibility failure.",
    ),
)

BY_NAME = {operator.name: operator for operator in OPERATORS}


def get_operator(name: str) -> Operator:
    try:
        return BY_NAME[name]
    except KeyError as exc:
        raise ValueError(f"unknown heuristic operator: {name}") from exc
