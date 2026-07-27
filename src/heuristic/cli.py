"""Public commands for validation, runs, resume, inspection, and comparison."""

from __future__ import annotations

import argparse
import json
import math
import shlex
import shutil
from pathlib import Path
from typing import Any

import yaml

from .bundle import CandidateBundleV1
from .contracts import Fidelity
from .evaluator import DockerEvaluator, DockerUnavailable
from .engines import OA_AVAILABLE, verify_gepa_oa
from .dgs import CodeEmbedder
from .knowledge import StrategyStore
from .plugins import LoadedProblem, load_problem
from .oa_runner import run_default_gepa
from .runner import (
    CommandSolver,
    HeuristicRunner,
    RunConfig,
    SeedSolver,
    UnifiedLLMSolver,
    UnifiedLLMSupport,
)
from .reporting import comparison_report, run_report
from .storage import ArtifactStore, HeuristicStore

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA = ROOT / ".solvita" / "heuristic"
ENGINES = {"solvita_dgs", "best_of_n", "random_qd", "default_gepa"}


def _baseline(problem: LoadedProblem) -> CandidateBundleV1:
    path = problem.root / problem.manifest.baseline_bundle
    return CandidateBundleV1({"main.cpp": path.read_text(encoding="utf-8")})


def _docker_baseline_check(
    problem: LoadedProblem, evaluator: DockerEvaluator
) -> dict[str, Any]:
    baseline = _baseline(problem)
    objectives: dict[str, float] = {}
    failures: dict[str, Any] = {}
    for instance_id in problem.adapter.discover_instances():
        record = evaluator.evaluate(baseline, instance_id, Fidelity.SEARCH, 0)
        if not record.feasible or record.objective is None:
            failures[instance_id] = record.failure or "infeasible"
        else:
            objectives[instance_id] = record.objective
    return {
        "status": "passed" if not failures else "failed",
        "feasible": len(objectives),
        "total": len(objectives) + len(failures),
        "failures": failures,
        "objective_min": min(objectives.values()) if objectives else None,
        "objective_max": max(objectives.values()) if objectives else None,
    }


def validate_problem(name: str, *, verify_baseline: bool = True) -> dict[str, Any]:
    problem = load_problem(name)
    train, validation = problem.adapter.split()
    if len(set(train) & set(validation)):
        raise ValueError("training and validation splits overlap")
    if sorted(train + validation) != problem.adapter.discover_instances():
        raise ValueError("split does not cover the declared instances")
    docker_status: dict[str, Any]
    evaluator = DockerEvaluator(
        problem.manifest,
        problem.adapter,
        sdk_dir=problem.root / "sdk",
    )
    try:
        docker_status = {"status": "available", **evaluator.preflight()}
    except DockerUnavailable as exc:
        docker_status = {"status": "unavailable", "reason": str(exc)}
    return {
        "problem": problem.manifest.problem_id,
        "manifest_digest": problem.manifest.digest(),
        "adapter_hash": problem.adapter.hash(),
        "train": train,
        "validation": validation,
        "split_counts": {"train": len(train), "validation": len(validation)},
        "docker_required": True,
        "docker": docker_status,
        "gepa_oa": {
            "status": "available" if OA_AVAILABLE else "unavailable",
            "required_commit": "f919db0a622e2e9f9204779b81fe00cc1b2d808f",
        },
        "default_standard": problem.manifest.default_standard,
        "baseline": (
            _docker_baseline_check(problem, evaluator)
            if verify_baseline and docker_status["status"] == "available"
            else {"status": ("skipped" if not verify_baseline else "unavailable")}
        ),
    }


def _paths(data_dir: Path) -> tuple[HeuristicStore, ArtifactStore]:
    data_dir.mkdir(parents=True, exist_ok=True)
    return HeuristicStore(data_dir / "heuristic.sqlite3"), ArtifactStore(
        data_dir / "artifacts"
    )


def _execute_run(
    *,
    problem_name: str,
    engine: str,
    run_id: str,
    proposals: int,
    support_calls: int,
    data_dir: Path,
    solver_command: str | None,
    smoke_seed: bool,
    early_stopping: bool = True,
) -> dict[str, Any]:
    if engine not in ENGINES:
        raise ValueError(f"unsupported engine {engine}")
    problem = load_problem(problem_name)
    store, artifacts = _paths(data_dir)
    baseline = _baseline(problem)
    if smoke_seed:
        solver = SeedSolver(baseline)
        support = None
    elif solver_command:
        solver = CommandSolver(shlex.split(solver_command))
        support = UnifiedLLMSupport({})
    else:
        solver = UnifiedLLMSolver({})
        support = UnifiedLLMSupport({})
    evaluator = DockerEvaluator(
        problem.manifest,
        problem.adapter,
        sdk_dir=problem.root / "sdk",
        cache_dir=data_dir / "compile",
        artifacts=artifacts,
        store=store,
    )
    docker_identity = evaluator.preflight()  # never fall back to native execution
    verify_gepa_oa()
    if engine == "default_gepa":
        custom_proposer = None
        if smoke_seed:

            def custom_proposer(
                candidate, reflective_dataset, components_to_update, metadata=None
            ):
                return {
                    key: value
                    for key, value in candidate.items()
                    if key in components_to_update
                }

        result = run_default_gepa(
            problem=problem,
            evaluator=evaluator,
            store=store,
            baseline=baseline,
            run_id=run_id,
            proposals=proposals,
            output_dir=data_dir / "oa" / run_id,
            custom_candidate_proposer=custom_proposer,
        )
        store.close()
        return {
            "run_id": run_id,
            "problem": problem_name,
            "engine": engine,
            "status": "completed",
            **result,
        }
    CodeEmbedder(strict=True).preflight()
    strategy_store = StrategyStore(data_dir / "strategies.sqlite3")
    runner = HeuristicRunner(
        problem=problem,
        evaluator=evaluator,
        store=store,
        artifacts=artifacts,
        solver=solver,
        config=RunConfig(
            run_id=run_id,
            engine=engine,
            proposals=proposals,
            support_calls=support_calls,
            early_stopping=early_stopping,
            plugin_hash=problem.adapter.hash(),
            manifest_digest=problem.manifest.digest(),
            language_standard=problem.manifest.default_standard,
            image_digest=docker_identity["image_digest"],
        ),
        support=support,
        strategy_store=strategy_store,
    )
    state = runner.run(baseline)
    strategy_store.close()
    store.close()
    return {
        "run_id": run_id,
        "problem": problem_name,
        "engine": engine,
        "proposals": state.proposals,
        "support_calls": state.support_calls,
        "evaluation_calls": state.evaluation_calls,
        "best_training": state.best_training
        if math.isfinite(state.best_training)
        else None,
        "best_validation_lcb": state.best_validation_lcb
        if math.isfinite(state.best_validation_lcb)
        else None,
        "status": "completed" if state.should_stop() else "running",
    }


def _inspect(run_id: str, data_dir: Path) -> dict[str, Any]:
    store, _ = _paths(data_dir)
    checkpoint = store.load_checkpoint(run_id)
    events = store.events(run_id)
    report = run_report(store, run_id)
    store.close()
    if checkpoint is None:
        raise ValueError(f"unknown run id: {run_id}")
    return {
        "run_id": run_id,
        "checkpoint": checkpoint,
        "events": len(events),
        "last_event": events[-1] if events else None,
        "report": report,
    }


def _export(run_id: str, data_dir: Path, output: Path | None) -> dict[str, str]:
    store, artifacts = _paths(data_dir)
    events = store.events(run_id)
    if not events:
        store.close()
        raise ValueError(f"unknown or empty run id: {run_id}")
    transitions = store.transitions(run_id)
    evaluations = store.evaluation_records(
        [transition["child_hash"] for transition in transitions]
    )
    checkpoint = store.load_checkpoint(run_id)
    report = run_report(store, run_id)
    output = output or data_dir / "exports" / f"{run_id}.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(
                json.dumps({"record_type": "event", **event}, sort_keys=True) + "\n"
            )
        for transition in transitions:
            handle.write(
                json.dumps({"record_type": "transition", **transition}, sort_keys=True)
                + "\n"
            )
        for evaluation in evaluations:
            handle.write(
                json.dumps({"record_type": "evaluation", **evaluation}, sort_keys=True)
                + "\n"
            )
        handle.write(
            json.dumps(
                {"record_type": "checkpoint", "payload": checkpoint}, sort_keys=True
            )
            + "\n"
        )
    result = {"trajectory": str(output)}
    best_hash = report.get("best_candidate_hash")
    candidate = store.candidate(str(best_hash)) if best_hash else None
    if candidate is not None:
        bundle = CandidateBundleV1.from_json(
            artifacts.read_bytes(candidate["bundle_artifact"], ".bundle.json").decode(
                "utf-8"
            )
        )
        bundle_dir = output.parent / f"{run_id}-best"
        if bundle_dir.exists():
            shutil.rmtree(bundle_dir)
        bundle.write(bundle_dir)
        canonical_path = bundle_dir / "candidate.bundle.json"
        canonical_path.write_text(bundle.canonical_json() + "\n", encoding="utf-8")
        result.update(
            {
                "best_candidate_hash": bundle.digest,
                "best_bundle": str(canonical_path),
                "best_source_dir": str(bundle_dir),
            }
        )
    store.close()
    return result


def _compare(
    experiment: Path,
    *,
    execute: bool = False,
    data_dir: Path = DEFAULT_DATA,
    solver_command: str | None = None,
    smoke_seed: bool = False,
    early_stopping: bool = True,
) -> dict[str, Any]:
    raw = yaml.safe_load(experiment.read_text(encoding="utf-8")) or {}
    engines = raw.get(
        "engines", ["best_of_n", "random_qd", "default_gepa", "solvita_dgs"]
    )
    replicates = int(raw.get("replicates", 3))
    proposals = int(raw.get("proposals", 200))
    runs = [
        {
            "engine": engine,
            "replicate": replicate,
            "proposals": proposals,
            "run_id": f"{raw.get('name', experiment.stem)}-{engine}-{replicate}",
        }
        for engine in engines
        for replicate in range(1, replicates + 1)
    ]
    result: dict[str, Any] = {
        "experiment": raw.get("name", experiment.stem),
        "runs": runs,
        "total_runs": len(runs),
    }
    if execute:
        result["results"] = [
            _execute_run(
                problem_name=str(raw.get("problem", "ogc")),
                engine=str(run["engine"]),
                run_id=str(run["run_id"]),
                proposals=int(run["proposals"]),
                support_calls=int(raw.get("support_calls", 40)),
                data_dir=data_dir,
                solver_command=solver_command,
                smoke_seed=smoke_seed,
                early_stopping=early_stopping,
            )
            for run in runs
        ]
        store, _ = _paths(data_dir)
        result["report"] = comparison_report(
            store, [str(run["run_id"]) for run in runs]
        )
        store.close()
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.heuristic.cli")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate-problem")
    validate.add_argument("--problem", required=True)
    validate.add_argument("--skip-baseline", action="store_true")
    run = sub.add_parser("run")
    run.add_argument("--problem", required=True)
    run.add_argument("--engine", default="solvita_dgs")
    run.add_argument("--run-id", default="local")
    run.add_argument("--proposals", type=int, default=200)
    run.add_argument("--support-calls", type=int, default=40)
    run.add_argument("--solver-command")
    run.add_argument("--smoke-seed", action="store_true")
    run.add_argument("--full-budget", action="store_true")
    resume = sub.add_parser("resume")
    resume.add_argument("--run-id", required=True)
    resume.add_argument("--problem", default="ogc")
    resume.add_argument("--engine", default="solvita_dgs")
    resume.add_argument("--proposals", type=int, default=200)
    resume.add_argument("--support-calls", type=int, default=40)
    resume.add_argument("--solver-command")
    resume.add_argument("--smoke-seed", action="store_true")
    resume.add_argument("--full-budget", action="store_true")
    inspect = sub.add_parser("inspect")
    inspect.add_argument("--run-id", required=True)
    export = sub.add_parser("export-trajectories")
    export.add_argument("--run-id", required=True)
    export.add_argument("--output", type=Path)
    compare = sub.add_parser("compare")
    compare.add_argument("--experiment", type=Path, required=True)
    compare.add_argument("--execute", action="store_true")
    compare.add_argument("--solver-command")
    compare.add_argument("--smoke-seed", action="store_true")
    compare.add_argument("--full-budget", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "validate-problem":
        result = validate_problem(args.problem, verify_baseline=not args.skip_baseline)
    elif args.command in {"run", "resume"}:
        result = _execute_run(
            problem_name=args.problem,
            engine=args.engine,
            run_id=args.run_id,
            proposals=args.proposals,
            support_calls=args.support_calls,
            data_dir=args.data_dir,
            solver_command=args.solver_command,
            smoke_seed=args.smoke_seed,
            early_stopping=not args.full_budget,
        )
    elif args.command == "inspect":
        result = _inspect(args.run_id, args.data_dir)
    elif args.command == "export-trajectories":
        result = _export(args.run_id, args.data_dir, args.output)
    else:
        result = _compare(
            args.experiment,
            execute=args.execute,
            data_dir=args.data_dir,
            solver_command=args.solver_command,
            smoke_seed=args.smoke_seed,
            early_stopping=not args.full_budget,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
