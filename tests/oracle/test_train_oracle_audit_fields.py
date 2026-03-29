import subprocess

import scripts.train_oracle as train_oracle


def test_build_candidate_audit_fields_classifies_zero_certified_reject():
    tests = {
        "ready": True,
        "generated_tests": [{"type": "public"}],
        "oracle_compile_success": True,
        "oracle_public_self_check_pass": True,
        "oracle_probe_pack_pass": True,
        "accepted_artifact_kind": None,
        "certified_count": 0,
        "certified_target_count": 50,
        "cert_ratio": 0.0,
        "checker_fallback_used": False,
        "solver_attempt_count": 5,
        "selected_template_name": "Expected Component-Cost via Pairwise Separation Probabilities",
        "prompt_char_stats": {"solver": 4669},
        "compact_retry_count": 0,
    }

    audit = train_oracle._build_candidate_audit_fields(tests, reward=-0.7)

    assert audit["decision"] == "reject"
    assert audit["reward_reason"] == "zero_certified_outputs"
    assert audit["failure_stage"] == "micro_test_certification"
    assert audit["failure_subtype"] == "empty_certification_set"
    assert audit["certified_count"] == 0
    assert audit["certified_target_count"] == 50
    assert audit["selected_template_name"] == (
        "Expected Component-Cost via Pairwise Separation Probabilities"
    )


def test_build_training_state_snapshot_keeps_oracle_event_metadata():
    state = {
        "config": {"trainable_memory": {"enabled": True}},
        "problem": {"description": "demo"},
        "status": "pending",
        "oracle_event_metadata": {
            "artifact_kind": "expected_output",
            "certified_count": 42,
            "failure_stage": "",
        },
    }
    tests = {
        "total_tests": 12,
        "test_results": [],
        "accepted_artifact_kind": "expected_output",
        "certification_evidence": [{"compile_success": True}],
        "verifier_provenance": None,
    }

    snapshot = train_oracle._build_training_state_snapshot(
        state=state,
        config=state["config"],
        trial_idx=7,
        tests=tests,
        route="exact_single_answer",
        oracle_ids=["oracle.dp.topdown"],
        pass_rate=0.615,
    )

    assert snapshot["oracle_event_metadata"]["artifact_kind"] == "expected_output"
    assert snapshot["oracle_event_metadata"]["certified_count"] == 42
    assert snapshot["tests"]["pass_rate"] == 0.615


def test_settle_memory_preserves_snapshot_fields_for_oracle_memory(monkeypatch):
    state = {
        "config": {
            "trainable_memory": {
                "enabled": True,
                "data_dir": "data/memory",
                "oracle_memory_mode": "updated",
                "oracle_memory_snapshot_id": "oracle_memory_mvp_v1",
                "skip_oracle_memory_rebuild": False,
                "oracle_memory_output_dir": "data/oracle_memory_models",
            }
        },
        "raw_problem": {"problem_id": "demo-problem"},
        "problem": {"description": "demo"},
        "status": "pending",
        "oracle_memory_decision": {
            "selected_action": "template.bucket.dp",
            "candidate_action_set": ["template.bucket.dp", "template.bucket.greedy"],
            "memory_mode": "updated",
        },
        "oracle_event_metadata": {
            "artifact_kind": "expected_output",
            "memory_mode": "updated",
            "selected_action": "template.bucket.dp",
            "candidate_action_set": ["template.bucket.dp", "template.bucket.greedy"],
        },
    }
    tests = {
        "total_tests": 12,
        "test_results": [],
        "accepted_artifact_kind": "expected_output",
        "certification_evidence": [{"compile_success": True}],
        "verifier_provenance": None,
    }

    snapshot = train_oracle._build_training_state_snapshot(
        state=state,
        config=state["config"],
        trial_idx=8,
        tests=tests,
        route="exact_single_answer",
        oracle_ids=["oracle.dp.topdown"],
        pass_rate=0.75,
    )

    captured = {}

    def fake_update_oracle_memory_node(settled_snapshot):
        captured["state_snapshot"] = settled_snapshot

    monkeypatch.setattr(train_oracle, "update_oracle_memory_node", fake_update_oracle_memory_node)

    train_oracle._settle_memory(
        {
            "id": "problem-1",
            "reward": 1.0,
            "state_snapshot": snapshot,
        }
    )

    settled_snapshot = captured["state_snapshot"]
    assert settled_snapshot["raw_problem"]["problem_id"] == "demo-problem"
    assert settled_snapshot["oracle_event_metadata"]["memory_mode"] == "updated"
    assert settled_snapshot["oracle_event_metadata"]["selected_action"] == "template.bucket.dp"
    assert settled_snapshot["oracle_event_metadata"]["candidate_action_set"] == [
        "template.bucket.dp",
        "template.bucket.greedy",
    ]
    assert settled_snapshot["tests"]["oracle_memory_decision"] == state["oracle_memory_decision"]


def test_rebuild_oracle_memory_snapshot_uses_updated_mode_config(monkeypatch):
    recorded = {}

    class DummyCompletedProcess:
        def __init__(self):
            self.stdout = '{"snapshot_id":"oracle_memory_mvp_v1"}'
            self.stderr = ""

    def fake_run(cmd, check, capture_output, text):
        recorded["cmd"] = cmd
        recorded["check"] = check
        recorded["capture_output"] = capture_output
        recorded["text"] = text
        return DummyCompletedProcess()

    monkeypatch.setattr(train_oracle.subprocess, "run", fake_run)

    train_oracle._rebuild_oracle_memory_snapshot(
        {
            "trainable_memory": {
                "data_dir": "custom/memory",
                "oracle_memory_mode": "updated",
                "oracle_memory_snapshot_id": "oracle_memory_mvp_v1",
                "skip_oracle_memory_rebuild": False,
                "oracle_memory_output_dir": "custom/output",
            }
        }
    )

    assert recorded["cmd"][0] == train_oracle.sys.executable
    assert recorded["cmd"][1].endswith("scripts/rebuild_oracle_memory_db.py")
    assert recorded["cmd"][2:] == [
        "--data-dir",
        "custom/memory",
        "--snapshot-id",
        "oracle_memory_mvp_v1",
        "--output-dir",
        "custom/output",
        "--prefix",
        "oracle_memory_mvp_v1",
    ]
    assert recorded["check"] is True
    assert recorded["capture_output"] is True
    assert recorded["text"] is True


def test_rebuild_oracle_memory_snapshot_skips_when_rebuild_disabled(monkeypatch):
    called = False

    def fake_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("subprocess.run should not be called in skip mode")

    monkeypatch.setattr(train_oracle.subprocess, "run", fake_run)

    train_oracle._rebuild_oracle_memory_snapshot(
        {
            "trainable_memory": {
                "oracle_memory_mode": "updated",
                "skip_oracle_memory_rebuild": True,
            }
        }
    )

    assert called is False


def test_rebuild_oracle_memory_snapshot_skips_when_mode_is_not_updated(monkeypatch):
    called = False

    def fake_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("subprocess.run should not be called outside updated mode")

    monkeypatch.setattr(train_oracle.subprocess, "run", fake_run)

    train_oracle._rebuild_oracle_memory_snapshot(
        {
            "trainable_memory": {
                "oracle_memory_mode": "frozen",
                "skip_oracle_memory_rebuild": False,
            }
        }
    )

    assert called is False


def test_rebuild_oracle_memory_snapshot_warns_and_returns_on_subprocess_failure(monkeypatch):
    warnings = []

    def fake_run(*args, **kwargs):
        raise subprocess.CalledProcessError(
            returncode=1,
            cmd=args[0],
            output="",
            stderr="rebuild failed",
        )

    def fake_warning(message, *args):
        warnings.append(message.format(*args))

    monkeypatch.setattr(train_oracle.subprocess, "run", fake_run)
    monkeypatch.setattr(train_oracle.logger, "warning", fake_warning)

    train_oracle._rebuild_oracle_memory_snapshot(
        {
            "trainable_memory": {
                "oracle_memory_mode": "updated",
                "oracle_memory_snapshot_id": "oracle_memory_mvp_v1",
                "skip_oracle_memory_rebuild": False,
                "oracle_memory_output_dir": "custom/output",
                "data_dir": "custom/memory",
            }
        }
    )

    assert warnings


def test_rebuild_oracle_memory_snapshot_warns_and_returns_on_launch_error(monkeypatch):
    warnings = []

    def fake_run(*args, **kwargs):
        raise OSError("executable missing")

    def fake_warning(message, *args):
        warnings.append(message.format(*args))

    monkeypatch.setattr(train_oracle.subprocess, "run", fake_run)
    monkeypatch.setattr(train_oracle.logger, "warning", fake_warning)

    train_oracle._rebuild_oracle_memory_snapshot(
        {
            "trainable_memory": {
                "oracle_memory_mode": "updated",
                "oracle_memory_snapshot_id": "oracle_memory_mvp_v1",
                "skip_oracle_memory_rebuild": False,
                "oracle_memory_output_dir": "custom/output",
                "data_dir": "custom/memory",
            }
        }
    )

    assert warnings
