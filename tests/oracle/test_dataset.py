import json
from pathlib import Path

from src.oracle.dataset import append_candidate_record, build_candidate_record


def test_candidate_record_contains_training_features():
    rec = build_candidate_record(
        problem_id="p1",
        trainability_class="exact_single_answer",
        candidate_family_pool=["oracle.dp.topdown", "oracle.graph.all_paths"],
        selected_family_id="oracle.dp.topdown",
        fallback_family_id="oracle.graph.all_paths",
        compile_success=True,
        public_self_check_pass=True,
        probe_pack_pass=True,
        route="exact_single_answer",
        artifact_kind="expected_output",
        decision="accept",
        certified_count=42,
        certified_target_count=50,
        cert_ratio=0.84,
        reward=0.23,
        reward_reason="partial_certification",
        failure_stage="",
        failure_subtype="",
        checker_fallback_used=True,
        solver_attempt_count=3,
        selected_template_name="Top-down Memoized DP",
        prompt_char_stats={"solver": 4096},
        compact_retry_count=1,
    )
    assert rec["selected_family_id"] == "oracle.dp.topdown"
    assert rec["decision"] == "accept"
    assert rec["candidate_family_pool"] == ["oracle.dp.topdown", "oracle.graph.all_paths"]
    assert rec["fallback_family_id"] == "oracle.graph.all_paths"
    assert rec["certified_count"] == 42
    assert rec["certified_target_count"] == 50
    assert rec["cert_ratio"] == 0.84
    assert rec["reward"] == 0.23
    assert rec["reward_reason"] == "partial_certification"
    assert rec["checker_fallback_used"] is True
    assert rec["solver_attempt_count"] == 3
    assert rec["selected_template_name"] == "Top-down Memoized DP"
    assert rec["prompt_char_stats"] == {"solver": 4096}
    assert rec["compact_retry_count"] == 1


def test_append_candidate_record_writes_jsonl(tmp_path: Path):
    path = tmp_path / "records.jsonl"
    append_candidate_record(path, {"problem_id": "p1", "decision": "accept"})
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["problem_id"] == "p1"
