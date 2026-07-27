import os
import shutil
import subprocess

import pytest

from src.heuristic.bundle import CandidateBundleV1
from src.heuristic.contracts import EvaluationRecord
from src.heuristic.plugins import load_problem
from src.heuristic.runner import HeuristicRunner, RunConfig, SeedSolver
from src.heuristic.storage import ArtifactStore, HeuristicStore


class TrustedTestEvaluator:
    """Host evaluator only for the checked-in trusted baseline acceptance test."""

    def __init__(self, problem, binary, store):
        self.problem, self.binary, self.store = problem, binary, store

    def evaluate(self, bundle, instance_id, fidelity, seed=0):
        cached = self.store.get_evaluation(
            bundle.digest,
            self.problem.manifest.problem_id,
            instance_id,
            fidelity.value,
            seed,
            self.problem.manifest.scorer_version,
        )
        if cached:
            from src.heuristic.contracts import Fidelity

            cached["fidelity"] = Fidelity(cached["fidelity"])
            return EvaluationRecord(**cached)
        process = subprocess.run(
            [str(self.binary)],
            input=self.problem.adapter.instance_stdin(instance_id),
            capture_output=True,
            env={
                **os.environ,
                "SOLVITA_SEED": str(seed),
                "SOLVITA_TIME_LIMIT_MS": "1000",
            },
            check=True,
        )
        result = self.problem.adapter.validate(
            instance_id, self.problem.adapter.parse_output(process.stdout)
        )
        record = EvaluationRecord(
            bundle.digest,
            self.problem.manifest.problem_id,
            instance_id,
            fidelity,
            seed,
            self.problem.manifest.scorer_version,
            bool(result["feasible"]),
            float(result["objective"]),
            {key: float(result[key]) for key in ("obj1", "obj2", "obj3")},
        )
        self.store.save_evaluation(record)
        return record


@pytest.mark.skipif(
    not (shutil.which("g++") or shutil.which("clang++")),
    reason="C++ compiler unavailable",
)
def test_reduced_ogc_run_persists_and_resumes(tmp_path):
    problem = load_problem("ogc")
    compiler = shutil.which("g++") or shutil.which("clang++")
    binary = tmp_path / "baseline"
    subprocess.run(
        [
            compiler,
            "-std=c++23",
            "-O2",
            "-I",
            str(problem.root / "sdk"),
            str(problem.root / problem.manifest.baseline_bundle),
            "-o",
            str(binary),
        ],
        check=True,
    )
    baseline = CandidateBundleV1(
        {
            "main.cpp": (problem.root / problem.manifest.baseline_bundle).read_text(
                encoding="utf-8"
            )
        }
    )
    store = HeuristicStore(tmp_path / "run.sqlite3")
    artifacts = ArtifactStore(tmp_path / "artifacts")
    runner = HeuristicRunner(
        problem=problem,
        evaluator=TrustedTestEvaluator(problem, binary, store),
        store=store,
        artifacts=artifacts,
        solver=SeedSolver(baseline),
        config=RunConfig("reduced", proposals=1),
    )
    state = runner.run(baseline)
    assert state.proposals == 1
    assert state.evaluation_calls == 32
    assert len(store.transitions("reduced")) == 1
    assert store.load_checkpoint("reduced")["proposals"] == 1
    restored = HeuristicRunner(
        problem=problem,
        evaluator=TrustedTestEvaluator(problem, binary, store),
        store=store,
        artifacts=artifacts,
        solver=SeedSolver(baseline),
        config=RunConfig("reduced", proposals=1),
    ).run(baseline)
    assert restored.proposals == 1
    assert len(store.transitions("reduced")) == 1
