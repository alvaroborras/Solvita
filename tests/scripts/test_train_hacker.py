import scripts.train_hacker as train_hacker
import json
from pathlib import Path


def test_train_one_hacker_injects_buggy_code_into_solution_code(monkeypatch, tmp_path):
    item = {
        "id": "p1",
        "description": "desc",
        "incorrect_solution": [{"code": "int main(){return 0;}"}],
        "test_case": [],
    }
    captured = {}

    monkeypatch.setattr(train_hacker, "compile_cpp", lambda *a, **k: (True, "ok"))

    def fake_hack_test_node(state):
        captured["code"] = state["solution"]["code"]
        return {
            "hack_round": state.get("hack_round", 0) + 1,
            "hack_passed": True,
            "hacker_memory_item_ids": [],
            "sandbox_verdicts": [],
            "compile_failures": 0,
            "analyst_report": {},
            "generator_route_used": "semantic",
            "hack_result": "SAFE",
            "hack_failure_type": "NONE",
        }

    monkeypatch.setattr(train_hacker, "hack_test_node", fake_hack_test_node)
    monkeypatch.setattr(train_hacker, "settle_hacker_memory", lambda state: {"hacker_reward": 0.0})

    train_hacker.train_one_hacker(
        item,
        {"trainable_memory": {"enabled": True, "data_dir": str(tmp_path)}},
        0,
    )

    assert captured["code"] == "int main(){return 0;}"


def test_train_one_hacker_replays_hack_rounds_until_terminal(monkeypatch, tmp_path):
    item = {
        "id": "p2",
        "description": "desc",
        "incorrect_solution": [{"code": "int main(){return 0;}"}],
        "test_case": [],
    }
    calls = {"hack_test": 0}

    monkeypatch.setattr(train_hacker, "compile_cpp", lambda *a, **k: (True, "ok"))

    def fake_hack_test_node(state):
        calls["hack_test"] += 1
        return {
            "hack_round": state.get("hack_round", 0) + 1,
            "hack_passed": True,
            "hacker_memory_item_ids": ["id1"],
            "sandbox_verdicts": [],
            "compile_failures": 0,
            "analyst_report": {},
            "generator_route_used": "semantic",
            "hack_result": "SAFE",
            "hack_failure_type": "NONE",
        }

    monkeypatch.setattr(train_hacker, "hack_test_node", fake_hack_test_node)
    monkeypatch.setattr(train_hacker, "settle_hacker_memory", lambda state: {"hacker_reward": 0.2})

    result = train_hacker.train_one_hacker(
        item,
        {"trainable_memory": {"enabled": True, "data_dir": str(tmp_path)}, "max_hack_rounds": 3},
        0,
    )

    assert calls["hack_test"] == 3
    assert result["reward"] == 0.2


def test_resolve_training_judges_prefers_item_assets_over_config(tmp_path):
    checker_exe = tmp_path / "checker.exe"
    validator_exe = tmp_path / "validator.exe"
    checker_exe.write_text("", encoding="utf-8")
    validator_exe.write_text("", encoding="utf-8")

    item = {
        "id": "p4",
        "description": "desc",
        "incorrect_solution": [{"code": "int main(){return 0;}"}],
        "test_case": [],
        "checker_exe": str(checker_exe),
        "validator_exe": str(validator_exe),
    }

    resolved = train_hacker._resolve_training_judges(
        item,
        {
            "trainable_memory": {"enabled": True, "data_dir": str(tmp_path)},
            "offline_hacker_assets_by_problem_id": {
                "p4": {"checker_exe": "bad-checker", "validator_exe": "bad-validator"}
            },
        },
    )

    assert resolved["checker_exe"] == str(checker_exe)
    assert resolved["validator_exe"] == str(validator_exe)
    assert resolved["judge_mode"] == "checker"


def test_train_one_hacker_uses_generated_input_then_correct_runner_to_fill_expected_output(monkeypatch, tmp_path):
    item = {
        "id": "p5",
        "description": "desc",
        "incorrect_solution": [{"code": "int main(){return 0;}"}],
        "correct_solution": [{"code": "#include <iostream>\nint main(){std::cout<<42<<\"\\n\";}"}],
        "test_case": [],
    }

    monkeypatch.setattr(train_hacker, "compile_cpp", lambda *a, **k: (True, "ok"))
    monkeypatch.setattr(train_hacker, "_prepare_correct_runner", lambda *a, **k: ("cpp", tmp_path / "oracle"))
    monkeypatch.setattr(train_hacker, "_run_correct_runner", lambda *a, **k: (0, "42\n"))
    monkeypatch.setattr(
        train_hacker,
        "generate_hack_candidate",
        lambda state: {
            "hack_round": 1,
            "hacker_memory_item_ids": ["id1"],
            "analyst_report": {},
            "generator_route_used": "semantic",
            "generator_failure_kind": "",
            "generator_failure_reason": "",
            "generated_input": "1\n",
            "execution_log": ["ok"],
            "compile_failures": 0,
            "validator_rejection_reasons": [],
        },
    )

    def fake_execute_hack_candidate(*, exe_path, generated_input, expected_output="", checker_exe=None, **kwargs):
        assert generated_input == "1\n"
        assert expected_output == "42\n"
        assert checker_exe is None
        return {
            "hack_passed": False,
            "hack_failures": [{"type": "WA", "input": "1\n", "expected": "42"}],
            "sandbox_verdicts": [{"verdict": "VALID_AND_BREAK", "failure_type": "WA"}],
            "compile_failures": 0,
        }

    monkeypatch.setattr(train_hacker, "execute_hack_candidate", fake_execute_hack_candidate)
    monkeypatch.setattr(train_hacker, "settle_hacker_memory", lambda state: {"hacker_reward": 0.88})

    result = train_hacker.train_one_hacker(
        item,
        {"trainable_memory": {"enabled": True, "data_dir": str(tmp_path)}},
        0,
    )

    assert result["reward"] == 0.88


def test_hacker_checkpoint_round_trip(tmp_path):
    path = tmp_path / "hacker_checkpoint.json"
    signature = {"dataset": "demo.jsonl", "skip": 0, "limit": 10, "tags": None}

    chk = train_hacker._load_checkpoint(path, signature)
    assert chk["signature"] == signature
    assert chk["settled_ids"] == []

    chk["settled_ids"].append("p1")
    train_hacker._save_checkpoint(path, chk)

    reloaded = train_hacker._load_checkpoint(path, signature)
    assert reloaded["settled_ids"] == ["p1"]


def test_worker_attack_reinitializes_llm_client(monkeypatch, tmp_path):
    item = {
        "id": "p7",
        "description": "desc",
        "incorrect_solution": [{"code": "int main(){return 0;}"}],
        "test_case": [],
    }
    called = {"llm": 0}

    class DummyClient:
        def __init__(self, config):
            called["llm"] += 1

    monkeypatch.setattr("src.llm.unified_client.UnifiedLLMClient", DummyClient)
    monkeypatch.setattr("src.llm.unified_client.set_default_client", lambda client: None)
    monkeypatch.setattr(train_hacker, "_run_hacker_training_state", lambda *a, **k: {"id": "p7", "reward": 0.0})

    result = train_hacker._worker_attack(
        item,
        {"trainable_memory": {"enabled": True, "data_dir": str(tmp_path)}},
        0,
    )

    assert called["llm"] == 1
    assert result["id"] == "p7"


def test_train_one_hacker_appends_candidate_record_when_path_configured(monkeypatch, tmp_path):
    item = {
        "id": "p8",
        "description": "desc",
        "incorrect_solution": [{"code": "int main(){return 0;}"}],
        "test_case": [],
    }
    output_path = tmp_path / "hacker_candidate_records.jsonl"

    monkeypatch.setattr(train_hacker, "compile_cpp", lambda *a, **k: (True, "ok"))

    def fake_hack_test_node(state):
        return {
            "hack_round": state.get("hack_round", 0) + 1,
            "hack_passed": False,
            "hacker_memory_item_ids": ["id1"],
            "sandbox_verdicts": [{"verdict": "VALID_AND_BREAK", "failure_type": "WA"}],
            "compile_failures": 0,
            "analyst_report": {},
            "generator_route_used": "semantic",
            "hack_result": "BREAK",
            "hack_failure_type": "WA",
            "generator_failure_kind": "",
        }

    monkeypatch.setattr(train_hacker, "hack_test_node", fake_hack_test_node)
    monkeypatch.setattr(train_hacker, "settle_hacker_memory", lambda state: {"hacker_reward": 0.88})

    train_hacker.train_one_hacker(
        item,
        {
            "trainable_memory": {"enabled": True, "data_dir": str(tmp_path)},
            "hacker_candidate_records_path": str(output_path),
        },
        0,
    )

    lines = output_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["problem_id"] == "p8"
    assert row["route_used"] == "semantic"
    assert row["hack_result"] == "BREAK"
    assert row["failure_type"] == "WA"
    assert row["reward"] == 0.88


def test_main_skips_checkpointed_problem_in_single_worker(monkeypatch, tmp_path):
    dataset_path = tmp_path / "dataset.jsonl"
    dataset_path.write_text(
        "\n".join(
            [
                json.dumps({"id": "p1", "description": "d1", "incorrect_solution": [{"code": "int main(){return 0;}"}]}),
                json.dumps({"id": "p2", "description": "d2", "incorrect_solution": [{"code": "int main(){return 0;}"}]}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    checkpoint_dir = tmp_path / "ckpt"
    checkpoint_dir.mkdir()
    signature = {
        "dataset": str(dataset_path.resolve()),
        "skip": 0,
        "limit": None,
        "tags": None,
    }
    checkpoint_path = checkpoint_dir / "hacker_checkpoint.json"
    checkpoint_path.write_text(
        json.dumps(
            {
                "signature": signature,
                "settled_ids": ["p1"],
                "error_ids": [],
                "last_updated": "",
                "stopped_reason": None,
            }
        ),
        encoding="utf-8",
    )

    processed = []

    class DummyClient:
        def __init__(self, config):
            self.config = config

    monkeypatch.setattr("src.llm.unified_client.UnifiedLLMClient", DummyClient)
    monkeypatch.setattr("src.llm.unified_client.set_default_client", lambda client: None)

    def fake_run_hacker_training_state(item, config, trial_idx):
        processed.append(item["id"])
        return {
            "id": item["id"],
            "state_snapshot": {
                "config": config,
                "generator_route_used": "semantic",
                "hack_result": "SAFE",
                "hack_failure_type": "NONE",
                "generator_failure_kind": "",
                "sandbox_verdicts": [],
                "compile_failures": 0,
            },
            "hack_success": False,
            "hacker_ids": [],
        }

    monkeypatch.setattr(train_hacker, "_run_hacker_training_state", fake_run_hacker_training_state)
    monkeypatch.setattr(train_hacker, "_settle_memory", lambda result: result.update({"reward": 0.0}))

    argv = [
        "train_hacker.py",
        "--dataset",
        str(dataset_path),
        "--checkpoint-dir",
        str(checkpoint_dir),
        "--data-dir",
        str(tmp_path / "memory"),
    ]
    monkeypatch.setattr("sys.argv", argv)

    train_hacker.main()

    assert processed == ["p2"]


def test_main_passes_candidate_records_path_to_training_config(monkeypatch, tmp_path):
    dataset_path = tmp_path / "dataset.jsonl"
    dataset_path.write_text(
        json.dumps(
            {
                "id": "p1",
                "description": "d1",
                "incorrect_solution": [{"code": "int main(){return 0;}"}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    output_path = tmp_path / "candidate_records.jsonl"
    captured = {}

    class DummyClient:
        def __init__(self, config):
            self.config = config

    monkeypatch.setattr("src.llm.unified_client.UnifiedLLMClient", DummyClient)
    monkeypatch.setattr("src.llm.unified_client.set_default_client", lambda client: None)

    def fake_run_hacker_training_state(item, config, trial_idx):
        captured["config"] = config
        return {
            "id": item["id"],
            "state_snapshot": {
                "config": config,
                "generator_route_used": "semantic",
                "hack_result": "SAFE",
                "hack_failure_type": "NONE",
                "generator_failure_kind": "",
                "sandbox_verdicts": [],
                "compile_failures": 0,
            },
            "hack_success": False,
            "hacker_ids": [],
        }

    monkeypatch.setattr(train_hacker, "_run_hacker_training_state", fake_run_hacker_training_state)
    monkeypatch.setattr(train_hacker, "_settle_memory", lambda result: result.update({"reward": 0.0}))

    argv = [
        "train_hacker.py",
        "--dataset",
        str(dataset_path),
        "--data-dir",
        str(tmp_path / "memory"),
        "--hacker-candidate-records-path",
        str(output_path),
    ]
    monkeypatch.setattr("sys.argv", argv)

    train_hacker.main()

    assert captured["config"]["hacker_candidate_records_path"] == str(output_path)


def test_main_snapshots_memory_every_n_settled(monkeypatch, tmp_path):
    dataset_path = tmp_path / "dataset.jsonl"
    dataset_path.write_text(
        "\n".join(
            [
                json.dumps({"id": "p1", "description": "d1", "incorrect_solution": [{"code": "int main(){return 0;}"}]}),
                json.dumps({"id": "p2", "description": "d2", "incorrect_solution": [{"code": "int main(){return 0;}"}]}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    data_dir = tmp_path / "memory"
    checkpoint_dir = tmp_path / "ckpt"
    snapshot_dir = tmp_path / "snapshots"
    checkpoint_dir.mkdir()

    class DummyClient:
        def __init__(self, config):
            self.config = config

    monkeypatch.setattr("src.llm.unified_client.UnifiedLLMClient", DummyClient)
    monkeypatch.setattr("src.llm.unified_client.set_default_client", lambda client: None)

    def fake_run_hacker_training_state(item, config, trial_idx):
        return {
            "id": item["id"],
            "state_snapshot": {
                "config": config,
                "generator_route_used": "semantic",
                "hack_result": "SAFE",
                "hack_failure_type": "NONE",
                "generator_failure_kind": "",
                "sandbox_verdicts": [],
                "compile_failures": 0,
            },
            "hack_success": False,
            "hacker_ids": [],
        }

    def fake_settle_memory(result):
        memory_file = Path(result["state_snapshot"]["config"]["trainable_memory"]["data_dir"]) / "hack" / "memory.db"
        memory_file.parent.mkdir(parents=True, exist_ok=True)
        memory_file.write_text(f"settled:{result['id']}", encoding="utf-8")
        result["reward"] = 0.0
        return result

    monkeypatch.setattr(train_hacker, "_run_hacker_training_state", fake_run_hacker_training_state)
    monkeypatch.setattr(train_hacker, "_settle_memory", fake_settle_memory)

    argv = [
        "train_hacker.py",
        "--dataset",
        str(dataset_path),
        "--data-dir",
        str(data_dir),
        "--checkpoint-dir",
        str(checkpoint_dir),
        "--memory-snapshot-every",
        "2",
        "--memory-snapshot-dir",
        str(snapshot_dir),
    ]
    monkeypatch.setattr("sys.argv", argv)

    train_hacker.main()

    snapshot_root = snapshot_dir / "step_000002"
    assert (snapshot_root / "memory" / "hack" / "memory.db").exists()
    assert (snapshot_root / "hacker_checkpoint.json").exists()
    meta = json.loads((snapshot_root / "snapshot_meta.json").read_text(encoding="utf-8"))
    assert meta["step"] == 2
    assert meta["settled_count"] == 2
    assert meta["error_count"] == 0
