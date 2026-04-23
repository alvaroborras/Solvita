import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_SCRIPT = REPO_ROOT / "scripts" / "run_oracle_memory_full_screen.sh"
STATUS_SCRIPT = REPO_ROOT / "scripts" / "check_oracle_memory_full_status.sh"


def _base_env(tmp_path: Path) -> dict[str, str]:
    dataset_path = tmp_path / "dummy_dataset.jsonl"
    dataset_path.write_text('{"id":"p1"}\n', encoding="utf-8")
    env = os.environ.copy()
    env.update(
        {
            "WORKTREE_DIR": str(tmp_path),
            "CONFIG_PATH": str(tmp_path / "oracle_memory_full_screen_config.json"),
            "LOG_FILE": str(tmp_path / "oracle_memory_full.log"),
            "DATA_DIR": str(tmp_path / "data" / "memory_full"),
            "CHECKPOINT_DIR": str(tmp_path / "data" / "checkpoints_oracle_memory_full"),
            "ORACLE_MEMORY_OUTPUT_DIR": str(tmp_path / "data" / "oracle_memory_models"),
            "SCRIPT_TRAIN": str(REPO_ROOT / "scripts" / "train_oracle.py"),
            "PYTHON_BIN": sys.executable,
            "DATASET": str(dataset_path),
            "DRY_RUN": "1",
            "SESSION_NAME": "oracle-memory-full-test",
            "SNAPSHOT_ID": "oracle_memory_full_test",
            "LLM_API_KEY": "test-key-for-dry-run-scripts",
        }
    )
    return env


def test_run_oracle_memory_full_screen_script_writes_config_in_dry_run(tmp_path: Path) -> None:
    result = subprocess.run(
        ["bash", str(RUN_SCRIPT)],
        env=_base_env(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "status=dry_run" in result.stdout

    config_path = tmp_path / "oracle_memory_full_screen_config.json"
    assert config_path.exists()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert config["session_name"] == "oracle-memory-full-test"
    assert config["snapshot_id"] == "oracle_memory_full_test"
    assert config["train_command"][-2:] == ["--oracle-memory-output-dir", str(tmp_path / "data" / "oracle_memory_models")]


def test_check_oracle_memory_full_status_reports_not_started_without_config(tmp_path: Path) -> None:
    result = subprocess.run(
        ["bash", str(STATUS_SCRIPT)],
        env=_base_env(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "status=not_started" in result.stdout


def test_check_oracle_memory_full_status_can_prepare_resume_in_dry_run(tmp_path: Path) -> None:
    env = _base_env(tmp_path)
    subprocess.run(
        ["bash", str(RUN_SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    checkpoint_path = tmp_path / "data" / "checkpoints_oracle_memory_full" / "oracle_checkpoint.json"
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text(
        json.dumps(
            {
                "signature": {
                    "dataset": env["DATASET"],
                    "skip": 0,
                    "limit": None,
                    "tags": None,
                },
                "settled_ids": ["problem-a", "problem-b"],
                "error_ids": [],
                "stopped_reason": "interrupted",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        ["bash", str(STATUS_SCRIPT), "--resume"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "status=stopped" in result.stdout
    assert "action=would_resume" in result.stdout
    assert "checkpoint_settled=2" in result.stdout
