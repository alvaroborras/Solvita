"""Upstream optimize-anything execution for the default GEPA comparison."""

from __future__ import annotations

import contextlib
import io
import threading
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

from .bundle import CandidateBundleV1
from .contracts import Fidelity
from .engines import oa_engine_name, verify_gepa_oa
from .scoring import robust_aggregate, validation_gain, validation_lcb


def run_default_gepa(
    *,
    problem,
    evaluator,
    store,
    baseline: CandidateBundleV1,
    run_id: str,
    proposals: int,
    max_token_cost: float | None = None,
    output_dir: str | Path | None = None,
    custom_candidate_proposer=None,
) -> dict[str, Any]:
    """Run the upstream GEPA optimizer over canonical candidate bundles.

    Frozen validation is deliberately absent from the OA ``Task``. It is
    evaluated once, outside the optimizer, only for the returned candidate.
    """
    verify_gepa_oa()
    from gepa.oa import OptimizeAnythingConfig
    from gepa.optimize_anything import optimize_anything

    train, validation = problem.adapter.split()
    baselines: dict[str, float] = {}
    for instance_id in train:
        record = evaluator.evaluate(baseline, instance_id, Fidelity.SEARCH, 0)
        if not record.feasible or record.objective is None:
            raise RuntimeError(f"baseline infeasible on {instance_id}")
        baselines[instance_id] = record.objective

    search_calls: list[tuple[int, str, float]] = []
    call_lock = threading.Lock()
    next_call = 0

    def score(candidate_text: str, example: dict[str, str]):
        nonlocal next_call
        with call_lock:
            call_index = next_call
            next_call += 1
        if call_index >= proposals * len(train):
            with call_lock:
                search_calls.append((call_index, candidate_text, -3.0))
            return -3.0, {"failure": "evaluation_budget_exhausted"}
        instance_id = example["id"]
        try:
            bundle = CandidateBundleV1.from_json(candidate_text)
        except Exception as exc:
            call_score = -3.0
            info = {"failure": "malformed_bundle", "detail": str(exc)}
        else:
            record = evaluator.evaluate(bundle, instance_id, Fidelity.SEARCH, 0)
            if not record.feasible or record.objective is None:
                call_score = -3.0
                info = {"failure": record.failure}
            else:
                call_score = validation_gain(
                    record.objective,
                    baselines[instance_id],
                    minimize=getattr(problem.manifest, "objective", "minimize")
                    == "minimize",
                )
                info = {
                    "objective": record.objective,
                    "runtime_ms": record.runtime_ms,
                }
        with call_lock:
            search_calls.append((call_index, candidate_text, call_score))
        return call_score, info

    store.create_run(
        run_id,
        problem.manifest.problem_id,
        "default_gepa",
        {
            "proposals": proposals,
            "max_token_cost": max_token_cost,
            "plugin_hash": (
                problem.adapter.hash()
                if callable(getattr(problem.adapter, "hash", None))
                else "unversioned-test-adapter"
            ),
            "manifest_digest": (
                problem.manifest.digest()
                if callable(getattr(problem.manifest, "digest", None))
                else "unversioned-test-manifest"
            ),
            "language_standard": getattr(problem.manifest, "default_standard", "c++23"),
            "image_digest": str(
                getattr(evaluator, "_image_digest", "") or "trusted-test-evaluator"
            ),
        },
    )
    captured_stdout = io.StringIO()
    with contextlib.redirect_stdout(captured_stdout):
        result = optimize_anything(
            baseline.canonical_json(),
            evaluator=score,
            dataset=[{"id": instance_id} for instance_id in train],
            objective=(
                f"Improve the {problem.manifest.problem_id} "
                f"{getattr(problem.manifest, 'default_standard', 'c++23')} "
                "CandidateBundleV1. "
                "Return only canonical CandidateBundleV1 JSON; compilation "
                "and feasibility are hard gates."
            ),
            background=(
                "Candidates read the trusted adapter's instance format on stdin "
                "and emit its declared solution format. Validation data and "
                "trusted scorer internals are unavailable."
            ),
            config=OptimizeAnythingConfig(
                engine=oa_engine_name("default_gepa"),
                name=run_id,
                max_evals=proposals * len(train),
                max_token_cost=max_token_cost,
                output_dir=output_dir,
                engine_config={
                    "reflection": (
                        {"custom_candidate_proposer": custom_candidate_proposer}
                        if custom_candidate_proposer is not None
                        else {"reflection_lm": "openai/gpt-4o-mini"}
                    ),
                    "engine": {"seed": 0},
                },
            ),
        )
    minimize = getattr(problem.manifest, "objective", "minimize") == "minimize"
    baseline_60: dict[str, float] = {}
    for instance_id in train + validation:
        baseline_record = evaluator.evaluate(
            baseline, instance_id, Fidelity.PROMOTION, 0
        )
        if not baseline_record.feasible or baseline_record.objective is None:
            raise RuntimeError(f"60s baseline infeasible on {instance_id}")
        baseline_60[instance_id] = baseline_record.objective

    ordered_calls = sorted(search_calls)
    programs: list[tuple[int, str, float]] = []
    for start in range(0, len(ordered_calls), len(train)):
        chunk = ordered_calls[start : start + len(train)]
        if not chunk:
            continue
        candidate_text = Counter(row[1] for row in chunk).most_common(1)[0][0]
        programs.append(
            (
                len(programs) + 1,
                candidate_text,
                mean(row[2] for row in chunk),
            )
        )
    programs = programs[:proposals]
    boundaries = list(range(20, len(programs) + 1, 20))
    if programs and (not boundaries or boundaries[-1] != len(programs)):
        boundaries.append(len(programs))

    best_bundle = baseline
    best_validation_lcb = float("-inf")
    validation_scores: dict[str, float] = dict.fromkeys(validation, 0.0)
    promotion_calls = 0
    validation_calls = 0
    for epoch, boundary in enumerate(boundaries, 1):
        promoted_programs = sorted(
            programs[:boundary],
            key=lambda item: (-item[2], item[0]),
        )[:2]
        promoted: list[tuple[CandidateBundleV1, float]] = []
        for _, candidate_text, _ in promoted_programs:
            try:
                bundle = CandidateBundleV1.from_json(candidate_text)
            except Exception:
                bundle = CandidateBundleV1(
                    {"main.cpp": '#error "malformed GEPA candidate"\n'}
                )
            gains: list[float] = []
            for instance_id in train:
                record = evaluator.evaluate(bundle, instance_id, Fidelity.PROMOTION, 0)
                promotion_calls += 1
                gains.append(
                    validation_gain(
                        record.objective,
                        baseline_60[instance_id],
                        minimize=minimize,
                    )
                    if record.feasible and record.objective is not None
                    else -3.0
                )
            promoted.append((bundle, robust_aggregate(gains)))
        if not promoted:
            continue
        epoch_bundle, _ = max(promoted, key=lambda item: (item[1], item[0].digest))
        epoch_scores: dict[str, float] = {}
        epoch_feasible = True
        for instance_id in validation:
            record = evaluator.evaluate(
                epoch_bundle, instance_id, Fidelity.PROMOTION, 0
            )
            validation_calls += 1
            epoch_feasible = (
                epoch_feasible and record.feasible and record.objective is not None
            )
            epoch_scores[instance_id] = (
                validation_gain(
                    record.objective,
                    baseline_60[instance_id],
                    minimize=minimize,
                )
                if record.feasible and record.objective is not None
                else -3.0
            )
        epoch_lcb = (
            validation_lcb(epoch_scores.values()) if epoch_feasible else float("-inf")
        )
        if epoch_feasible and (
            epoch_lcb > best_validation_lcb
            or (
                epoch_lcb == best_validation_lcb
                and epoch_bundle.digest < best_bundle.digest
            )
        ):
            best_bundle = epoch_bundle
            best_validation_lcb = epoch_lcb
            validation_scores = epoch_scores
        store.append_event(
            "epoch_boundary",
            f"{run_id}:epoch:{epoch}",
            {
                "promoted": [bundle.digest for bundle, _ in promoted],
                "validation_candidate_hash": epoch_bundle.digest,
                "validation_feasible": epoch_feasible,
                "validation_epoch_lcb": epoch_lcb,
            },
            run_id=run_id,
            proposal=boundary,
        )
    validation_feasible = best_validation_lcb != float("-inf")
    rejected_candidate_hash = None
    if not validation_feasible:
        try:
            rejected_candidate_hash = CandidateBundleV1.from_json(
                result.best_candidate
            ).digest
        except Exception:
            rejected_candidate_hash = None
        best_bundle = baseline
        best_validation_lcb = 0.0
        validation_scores = dict.fromkeys(validation, 0.0)
        validation_feasible = True
    if getattr(evaluator, "artifacts", None) is not None:
        artifact = evaluator.artifacts.put_bytes(
            best_bundle.canonical_json().encode("utf-8"), ".bundle.json"
        )
        store.save_candidate(
            best_bundle.digest,
            artifact,
            problem.manifest.default_standard,
        )
    best_so_far: list[float] = []
    running_best = float("-inf")
    for _, _, program_score in programs:
        running_best = max(running_best, program_score)
        best_so_far.append(running_best)
    serializable_metadata = {
        key: value
        for key, value in (result.metadata or {}).items()
        if isinstance(value, (str, int, float, bool, type(None), list, dict))
    }
    payload = {
        "best_candidate_hash": best_bundle.digest,
        "rejected_candidate_hash": rejected_candidate_hash,
        "validation_feasible": validation_feasible,
        "best_score": result.best_score,
        "proposals": len(programs),
        "observed_search_calls": len(search_calls),
        "total_evals": result.total_evals,
        "evaluation_calls": result.total_evals + promotion_calls + validation_calls,
        "best_so_far": best_so_far,
        "validation_scores": validation_scores,
        "metadata": serializable_metadata,
        "oa_stdout": captured_stdout.getvalue()[-8000:],
    }
    store.append_event("oa_result", f"{run_id}:oa_result", payload, run_id=run_id)
    store.checkpoint(
        run_id,
        {
            "run_id": run_id,
            "proposals": len(programs),
            "support_calls": 0,
            "evaluation_calls": result.total_evals + promotion_calls + validation_calls,
            "best_training": result.best_score,
            "best_validation_lcb": (
                best_validation_lcb if validation_feasible else None
            ),
            "archive": {"entries": []},
            "metadata": {
                "cost": serializable_metadata.get("total_cost"),
                "tokens": serializable_metadata.get("total_tokens"),
            },
        },
    )
    store.set_run_status(run_id, "completed")
    return payload
