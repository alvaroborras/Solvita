import pytest


def test_custom_engines_register_and_run_through_pinned_oa(tmp_path):
    pytest.importorskip("gepa.oa")
    from gepa.oa import OptimizeAnythingConfig
    from gepa.oa.registry import get_engine_cls
    from gepa.optimize_anything import optimize_anything

    import src.heuristic.engines  # noqa: F401

    assert get_engine_cls("solvita_dgs").__name__ == "SolvitaDGSEngine"
    assert get_engine_cls("random_qd").__name__ == "RandomQDEngine"

    for engine in ("solvita_dgs", "random_qd"):
        result = optimize_anything(
            "seed",
            evaluator=lambda candidate, example: (
                float(len(candidate)),
                {"example": example["id"]},
            ),
            dataset=[{"id": "a"}, {"id": "b"}],
            objective="OA contract smoke",
            config=OptimizeAnythingConfig(
                engine=engine,
                max_evals=10,
                output_dir=tmp_path / engine,
                engine_config={"proposals": 2, "support_calls": 0},
            ),
        )
        assert result.best_candidate == "seed"
        assert result.total_evals == 4
        assert result.metadata["proposals"] == 2


def test_default_gepa_runner_keeps_validation_outside_task(tmp_path):
    pytest.importorskip("gepa.oa")
    from types import SimpleNamespace

    from src.heuristic.bundle import CandidateBundleV1
    from src.heuristic.contracts import EvaluationRecord
    from src.heuristic.oa_runner import run_default_gepa
    from src.heuristic.storage import HeuristicStore

    class Adapter:
        @staticmethod
        def split():
            return ["train"], ["validation"]

    class Evaluator:
        def __init__(self):
            self.calls = []

        def evaluate(self, bundle, instance_id, fidelity, seed):
            self.calls.append((instance_id, fidelity.value))
            return EvaluationRecord(
                bundle.digest,
                "fake",
                instance_id,
                fidelity,
                seed,
                "v1",
                True,
                10.0 if instance_id == "train" else 20.0,
            )

    manifest = SimpleNamespace(problem_id="fake")
    problem = SimpleNamespace(adapter=Adapter(), manifest=manifest)
    evaluator = Evaluator()
    store = HeuristicStore(tmp_path / "oa.sqlite3")
    baseline = CandidateBundleV1({"main.cpp": "int main(){}"})

    def proposer(candidate, reflective_dataset, components_to_update, metadata=None):
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
        run_id="oa",
        proposals=4,
        output_dir=tmp_path / "output",
        custom_candidate_proposer=proposer,
    )
    assert result["total_evals"] == 4
    assert ("validation", "60s") in evaluator.calls
    # Validation is evaluated only after GEPA's four-call training budget.
    assert evaluator.calls[:5] == [("train", "10s")] * 5


def test_upstream_best_of_n_engine_contract(monkeypatch, tmp_path):
    pytest.importorskip("gepa.oa")
    from gepa.oa import OptimizeAnythingConfig
    from gepa.optimize_anything import optimize_anything
    from gepa.oa.engines import best_of_n

    class FakeLM:
        def __init__(self, *args, **kwargs):
            self.total_cost = 0.0
            self.calls = 0

        def __call__(self, prompt):
            self.calls += 1
            return f"```\ncandidate-{self.calls}\n```"

    monkeypatch.setattr(best_of_n, "LM", FakeLM)
    result = optimize_anything(
        "seed",
        evaluator=lambda candidate, example: (
            float(len(candidate)),
            {"id": example["id"]},
        ),
        dataset=[{"id": "a"}, {"id": "b"}],
        objective="Best-of-N contract",
        config=OptimizeAnythingConfig(
            engine="best_of_n",
            max_evals=4,
            output_dir=tmp_path,
            engine_config={"model": "fake", "max_n": 2},
        ),
    )
    assert result.best_candidate == "candidate-1"
    assert result.total_evals == 4
