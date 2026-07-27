from types import SimpleNamespace

from src.heuristic.bundle import CandidateBundleV1
from src.heuristic.contracts import EvaluationRecord
from src.heuristic.knowledge import StrategyCard, StrategyStore
from src.heuristic.runner import HeuristicRunner, RunConfig
from src.heuristic.storage import ArtifactStore, HeuristicStore


class TinyAdapter:
    problem_id = "tiny"

    @staticmethod
    def split():
        return ["train"], ["validation"]

    @staticmethod
    def features(instance_id):
        return {"size": 1.0 if instance_id == "train" else 2.0}

    @staticmethod
    def hash():
        return "tiny-adapter-v1"


class TinyEvaluator:
    _image_digest = "sha256:" + "1" * 64

    @staticmethod
    def evaluate(bundle, instance_id, fidelity, seed):
        return EvaluationRecord(
            bundle.digest,
            "tiny",
            instance_id,
            fidelity,
            seed,
            "tiny-v1",
            True,
            100.0,
        )


class CountingSolver:
    def __init__(self):
        self.calls = []

    def generate(self, operator, parents, context):
        self.calls.append((operator, list(parents), dict(context)))
        return CandidateBundleV1(
            {
                "main.cpp": (
                    f"int main(){{return 0;}}\n// proposal {context['proposal']}\n"
                )
            }
        )


def test_exactly_one_solver_call_per_counted_proposal(tmp_path):
    manifest = SimpleNamespace(
        problem_id="tiny",
        problem_family="tiny",
        objective="minimize",
        default_standard="c++23",
        digest=lambda: "tiny-manifest-v1",
    )
    problem = SimpleNamespace(adapter=TinyAdapter(), manifest=manifest)
    store = HeuristicStore(tmp_path / "heuristic.sqlite3")
    solver = CountingSolver()
    strategies = StrategyStore(tmp_path / "strategies.sqlite3")
    strategies.put(
        StrategyCard(
            "tiny-card",
            "test strategy",
            domains=("tiny",),
            owner_problem="tiny",
        )
    )
    baseline = CandidateBundleV1({"main.cpp": "int main(){return 0;}\n"})
    state = HeuristicRunner(
        problem=problem,
        evaluator=TinyEvaluator(),
        store=store,
        artifacts=ArtifactStore(tmp_path / "artifacts"),
        solver=solver,
        config=RunConfig("cadence", proposals=17, support_calls=0),
        strategy_store=strategies,
    ).run(baseline)
    assert state.proposals == 17
    assert len(solver.calls) == 17
    assert len(store.transitions("cadence")) == 17
    assert all(
        context["mode"] == operator.mode for operator, _, context in solver.calls
    )
    assert all(not parents for _, parents, _ in solver.calls[:16])
    assert all(call[2]["strategies"] for call in solver.calls)
    evidence = strategies.evidence("tiny-card")
    assert evidence
    assert evidence[-1]["descendant_delta"] is not None
