import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.evaluate_oracle_memory_policy import main as evaluate_main
from scripts.train_oracle_memory_policy import main as train_main


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_audit_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _audit_row(
    problem_id: str,
    *,
    selected_template_name: str,
    decision: str,
    reward_reason: str,
) -> dict[str, object]:
    return {
        "problem_id": problem_id,
        "selected_template_name": selected_template_name,
        "decision": decision,
        "reward_reason": reward_reason,
        "source_path": "/runs/mock_selected_family/data/checkpoints/oracle_candidate_records.jsonl",
    }


def test_train_and_eval_cli_write_expected_artifacts_and_report_ranking_limits(tmp_path: Path):
    source_path = tmp_path / "source.jsonl"
    audit_a = tmp_path / "audit_a.csv"
    audit_b = tmp_path / "audit_b.csv"
    train_output_dir = tmp_path / "train_out"
    eval_output_dir = tmp_path / "eval_out"

    _write_jsonl(
        source_path,
        [
            {
                "id": "p1",
                "description": "Count paths on a tree with updates.",
                "tags": ["dp", "trees"],
                "test_case": [{"input": "3\n1 2\n2 3\n", "output": "2\n"}],
                "correct_solution": [{"code": "good"}],
                "incorrect_solution": [{"code": "bad"}],
            },
            {
                "id": "p2",
                "description": "Simulate operations on a grid.",
                "tags": ["implementation"],
                "test_case": [{"input": "2 2\n..\n..\n", "output": "4\n"}],
                "correct_solution": [{"code": "good"}],
                "incorrect_solution": [{"code": "bad"}],
            },
            {
                "id": "p3",
                "description": "Find shortest path variants.",
                "tags": ["graphs"],
                "test_case": [{"input": "4 4\n", "output": "1\n"}],
                "correct_solution": [{"code": "good"}],
                "incorrect_solution": [{"code": "bad"}],
            },
            {
                "id": "p4",
                "description": "Count valid pairs with dynamic programming.",
                "tags": ["dp", "math"],
                "test_case": [{"input": "5\n", "output": "10\n"}],
                "correct_solution": [{"code": "good"}],
                "incorrect_solution": [{"code": "bad"}],
            },
        ],
    )
    _write_audit_csv(
        audit_a,
        [
            _audit_row(
                "p1",
                selected_template_name="Top-down Memoized DP",
                decision="accept",
                reward_reason="fully_certified",
            ),
            _audit_row(
                "p2",
                selected_template_name="N-Nested Loops Simulation (Dynamic Depth DFS)",
                decision="accept",
                reward_reason="fully_certified",
            ),
        ],
    )
    _write_audit_csv(
        audit_b,
        [
            _audit_row(
                "p3",
                selected_template_name="Custom Template A",
                decision="reject",
                reward_reason="negative_reward",
            ),
            _audit_row(
                "p4",
                selected_template_name="Top-down Memoized DP",
                decision="reject",
                reward_reason="public_self_check_failed",
            ),
        ],
    )

    assert (
        train_main(
            [
                "--audit-csv",
                str(audit_a),
                "--audit-csv",
                str(audit_b),
                "--source-jsonl",
                str(source_path),
                "--output-dir",
                str(train_output_dir),
                "--prefix",
                "oracle_memory_policy_cli",
                "--min-bucket-examples",
                "1",
            ]
        )
        == 0
    )

    assert (train_output_dir / "oracle_memory_policy_cli_recipe_bucket_summary.json").exists()
    assert (train_output_dir / "oracle_memory_policy_cli_training_examples.csv").exists()
    assert (train_output_dir / "oracle_memory_policy_cli_model.json").exists()
    assert (train_output_dir / "oracle_memory_policy_cli_feature_weights.csv").exists()
    assert (train_output_dir / "oracle_memory_policy_cli_oof_predictions.csv").exists()
    assert (train_output_dir / "oracle_memory_policy_cli_selection_summary.json").exists()

    assert (
        evaluate_main(
            [
                "--training-examples-csv",
                str(train_output_dir / "oracle_memory_policy_cli_training_examples.csv"),
                "--model-json",
                str(train_output_dir / "oracle_memory_policy_cli_model.json"),
                "--output-dir",
                str(eval_output_dir),
                "--prefix",
                "oracle_memory_policy_cli",
            ]
        )
        == 0
    )

    eval_summary = json.loads(
        (eval_output_dir / "oracle_memory_policy_cli_eval_summary.json").read_text(encoding="utf-8")
    )
    assert "observed_action_metrics" in eval_summary
    assert "ranking_analysis" in eval_summary
    assert eval_summary["ranking_analysis"]["supported"] is False
    assert "insufficient_multi_bucket_problem_coverage" in eval_summary["ranking_analysis"]["limitation_reasons"]
    assert not (eval_output_dir / "oracle_memory_policy_cli_problem_rankings.csv").exists()
