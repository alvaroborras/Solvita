import json
from pathlib import Path

from src.heuristic.bundle import CandidateBundleV1
from src.heuristic.cli import _export
from src.heuristic.contracts import EvaluationRecord, Fidelity
from src.heuristic.reporting import comparison_report, run_report
from src.heuristic.storage import ArtifactStore, HeuristicStore


def _make_run(root: Path, run_id: str, engine: str) -> tuple[HeuristicStore, str]:
    store = HeuristicStore(root / "heuristic.sqlite3")
    artifacts = ArtifactStore(root / "artifacts")
    bundle = CandidateBundleV1({"main.cpp": "int main(){return 0;}\n"})
    artifact = artifacts.put_bytes(bundle.canonical_json().encode(), ".bundle.json")
    store.save_candidate(bundle.digest, artifact, "c++23")
    store.create_run(run_id, "ogc", engine, {"proposals": 1})
    record = EvaluationRecord(
        bundle.digest,
        "ogc",
        "prob_1",
        Fidelity.SEARCH,
        0,
        "v1",
        True,
        123.0,
    )
    checkpoint = {
        "run_id": run_id,
        "proposals": 1,
        "evaluation_calls": 1,
        "support_calls": 0,
        "best_training": 0.5,
        "best_validation_lcb": 0.1,
        "archive": {
            "entries": [
                {
                    "candidate_hash": bundle.digest,
                    "quality": 0.5,
                    "instance_scores": {"prob_1": 0.5},
                }
            ]
        },
    }
    store.commit_proposal(
        run_id=run_id,
        proposal=1,
        operator="new_paradigm",
        parent_hashes=[],
        child_hash=bundle.digest,
        transition={"quality": 0.5},
        evaluations=[record],
        checkpoint=checkpoint,
    )
    return store, bundle.digest


def test_reports_all_comparison_metrics_and_groups_engines(tmp_path):
    store, digest = _make_run(tmp_path, "dgs-1", "solvita_dgs")
    report = run_report(store, "dgs-1")
    assert report["best_candidate_hash"] == digest
    assert report["bottom_tail_quality"] == 0.5
    assert report["raw_objectives"]["10s"]["training"]["mean"] == 123.0
    assert report["wall_time_seconds"] == 0.0
    comparison = comparison_report(store, ["dgs-1"])
    assert comparison["by_engine"]["solvita_dgs"]["replicates"] == 1
    assert comparison["by_engine"]["solvita_dgs"]["mean_best_validation_lcb"] == 0.1
    store.close()


def test_trajectory_export_materializes_best_source_bundle(tmp_path):
    store, digest = _make_run(tmp_path, "export", "solvita_dgs")
    store.close()
    result = _export("export", tmp_path, tmp_path / "trajectory.jsonl")
    assert result["best_candidate_hash"] == digest
    source_dir = Path(result["best_source_dir"])
    assert (source_dir / "main.cpp").is_file()
    canonical = json.loads(Path(result["best_bundle"]).read_text())
    assert canonical["version"] == 1
    assert Path(result["trajectory"]).read_text().count("\n") == 4
