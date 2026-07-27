"""Recomputable scoring policies over immutable raw objectives."""

from __future__ import annotations

import math
import random
from statistics import mean, pstdev
from typing import Iterable, Mapping, Sequence


def bks_quality(
    objective: float,
    baseline: float,
    bks: float,
    *,
    minimize: bool = True,
    epsilon: float = 1e-9,
) -> float | None:
    gap = abs(baseline - bks)
    if gap <= epsilon:
        return None
    improvement = baseline - objective if minimize else objective - baseline
    return improvement / max(gap, epsilon)


def validation_gain(
    objective: float,
    baseline: float,
    *,
    minimize: bool = True,
    epsilon: float = 1e-9,
) -> float:
    improvement = baseline - objective if minimize else objective - baseline
    return improvement / max(abs(baseline), epsilon)


def standardized_raw_utilities(
    objectives: Sequence[float],
    *,
    minimize: bool = True,
) -> list[float]:
    if not objectives:
        return []
    raw = [-x if minimize else x for x in objectives]
    scale = pstdev(raw)
    standardized = [(x - mean(raw)) / scale if scale > 1e-12 else 0.0 for x in raw]
    denominator = max(1, len(raw) - 1)
    positions: dict[float, list[int]] = {}
    for position, index in enumerate(sorted(range(len(raw)), key=raw.__getitem__)):
        positions.setdefault(raw[index], []).append(position)
    rank_by_value = {
        value: mean(value_positions) / denominator
        for value, value_positions in positions.items()
    }
    ranks = [rank_by_value[value] for value in raw]
    return [0.75 * z + 0.25 * rank for z, rank in zip(standardized, ranks)]


def normalized_quality(
    objective: float,
    baseline: float,
    bks: float | None,
    *,
    minimize: bool = True,
    epsilon: float = 1e-9,
) -> float:
    """Compatibility helper: BKS quality or stationary baseline gain."""
    if bks is not None:
        quality = bks_quality(
            objective, baseline, bks, minimize=minimize, epsilon=epsilon
        )
        if quality is not None:
            return quality
    return validation_gain(objective, baseline, minimize=minimize, epsilon=epsilon)


def training_quality_matrix(
    candidate_objectives: Mapping[str, float | None],
    baselines: Mapping[str, float],
    bks_snapshot: Mapping[str, float],
    population_objectives: Mapping[str, Sequence[float]] | None = None,
    *,
    minimize: bool = True,
    invalid_target: float = -3.0,
) -> dict[str, float]:
    result: dict[str, float] = {}
    fallback_ids: list[str] = []
    for instance_id, objective in candidate_objectives.items():
        if objective is None or not math.isfinite(objective):
            result[instance_id] = invalid_target
            continue
        if instance_id in bks_snapshot:
            quality = bks_quality(
                objective,
                baselines[instance_id],
                bks_snapshot[instance_id],
                minimize=minimize,
            )
            if quality is not None:
                result[instance_id] = quality
                continue
        fallback_ids.append(instance_id)
    for instance_id in fallback_ids:
        raw_objective = candidate_objectives[instance_id]
        assert raw_objective is not None
        objective = float(raw_objective)
        population = list((population_objectives or {}).get(instance_id, [])) + [
            objective
        ]
        result[instance_id] = standardized_raw_utilities(population, minimize=minimize)[
            -1
        ]
    return result


def robust_aggregate(values: Iterable[float], tail_fraction: float = 0.2) -> float:
    vals = sorted(float(x) for x in values)
    if not vals:
        return float("-inf")
    tail_n = max(1, math.ceil(len(vals) * tail_fraction))
    return 0.70 * mean(vals) + 0.30 * mean(vals[:tail_n])


def validation_lcb(
    values: Iterable[float],
    confidence: float = 0.95,
    *,
    bootstrap_samples: int = 10_000,
    seed: int = 0,
) -> float:
    """One-sided bootstrap lower confidence bound over validation instances."""
    vals = [float(x) for x in values]
    if not vals:
        return float("-inf")
    if len(vals) == 1:
        return vals[0]
    rng = random.Random(seed)
    means = sorted(
        mean(vals[rng.randrange(len(vals))] for _ in vals)
        for _ in range(bootstrap_samples)
    )
    index = max(0, min(len(means) - 1, int((1.0 - confidence) * len(means))))
    return means[index]
