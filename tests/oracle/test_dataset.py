import json
from pathlib import Path

from src.oracle.dataset import append_candidate_record, build_candidate_record


def test_candidate_record_contains_training_features():
    rec = build_candidate_record(
        problem_id="p1",
        trainability_class="exact_single_answer",
        candidate_family_pool=["oracle.dp.topdown", "oracle.graph.all_paths"],
        selected_family_id="oracle.dp.topdown",
        compile_success=True,
        public_self_check_pass=True,
        probe_pack_pass=True,
        route="exact_single_answer",
        artifact_kind="expected_output",
        decision="accept",
    )
    assert rec["selected_family_id"] == "oracle.dp.topdown"
    assert rec["decision"] == "accept"
    assert rec["candidate_family_pool"] == ["oracle.dp.topdown", "oracle.graph.all_paths"]


def test_append_candidate_record_writes_jsonl(tmp_path: Path):
    path = tmp_path / "records.jsonl"
    append_candidate_record(path, {"problem_id": "p1", "decision": "accept"})
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["problem_id"] == "p1"
