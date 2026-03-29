import csv
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.oracle.oracle_memory_policy import (
    ONLINE_VISIBLE_SOURCE_FIELDS,
    build_training_examples,
    compute_description_statistics,
    compute_test_case_statistics,
    recipe_bucket_from_template_name,
    summarize_recipe_bucket_support,
    tokenize_description,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _audit_row(
    problem_id: str,
    *,
    selected_template_name: str,
    decision: str = "accept",
    reward_reason: str = "fully_certified",
) -> dict[str, str]:
    return {
        "problem_id": problem_id,
        "selected_template_name": selected_template_name,
        "decision": decision,
        "reward_reason": reward_reason,
        "source_path": "/runs/mock_selected_family/data/checkpoints/oracle_candidate_records.jsonl",
    }


def test_recipe_bucket_mapping_is_deterministic():
    assert recipe_bucket_from_template_name("Top-down Memoized DP") == "recipe.dp.memo_default"
    assert (
        recipe_bucket_from_template_name("N-Nested Loops Simulation (Dynamic Depth DFS)")
        == "recipe.enum.simulation_default"
    )
    assert recipe_bucket_from_template_name("BFS on Allowed Cells (Implicit Graph, Hash Set)") == (
        "recipe.specialized.other"
    )
    assert recipe_bucket_from_template_name("") == "recipe.specialized.other"


def test_summarize_recipe_bucket_support_groups_long_tail_templates():
    summary = summarize_recipe_bucket_support(
        [
            _audit_row("p1", selected_template_name="Top-down Memoized DP"),
            _audit_row("p2", selected_template_name="Top-down Memoized DP"),
            _audit_row("p3", selected_template_name="N-Nested Loops Simulation (Dynamic Depth DFS)"),
            _audit_row("p4", selected_template_name="Custom Template A"),
            _audit_row("p4", selected_template_name="Custom Template B"),
        ]
    )

    assert summary["bucket_counts"] == {
        "recipe.dp.memo_default": 2,
        "recipe.enum.simulation_default": 1,
        "recipe.specialized.other": 2,
    }
    assert summary["bucket_mapping"] == {
        "Top-down Memoized DP": "recipe.dp.memo_default",
        "N-Nested Loops Simulation (Dynamic Depth DFS)": "recipe.enum.simulation_default",
        "Custom Template A": "recipe.specialized.other",
        "Custom Template B": "recipe.specialized.other",
    }


def test_compute_test_case_statistics_extracts_required_shape_features():
    stats = compute_test_case_statistics(
        [
            {"input": "1 2\n3\n", "output": "6\n"},
            {"input": "10 20 30\n", "output": "60\n70\n"},
            {"input": "5\n", "output": "1\n"},
        ]
    )

    assert stats["num_tests"] == 3
    assert stats["median_input_chars"] == 6.0
    assert stats["max_input_chars"] == 9
    assert stats["median_output_chars"] == 2.0
    assert stats["max_output_chars"] == 6
    assert stats["median_input_lines"] == 1.0
    assert stats["median_output_lines"] == 1.0
    assert stats["token_count_input"] == 7
    assert stats["token_count_output"] == 4
    assert stats["digit_ratio_input"] > 0.5
    assert stats["digit_ratio_output"] > 0.5


def test_description_tokenization_and_statistics_are_normalized():
    text = "Count ways on TREE paths with 10 queries."
    assert tokenize_description(text) == ["count", "ways", "on", "tree", "paths", "with", "10", "queries"]

    stats = compute_description_statistics(text)
    assert stats["description_chars"] == len(text)
    assert stats["description_lines"] == 1
    assert stats["description_token_count"] == 8
    assert stats["description_digit_ratio"] > 0.0


def test_build_training_examples_uses_only_allowed_visible_fields(tmp_path: Path):
    source_path = tmp_path / "source.jsonl"
    _write_jsonl(
        source_path,
        [
            {
                "id": "p1",
                "description": "Count paths on a tree.",
                "tags": ["dp", "trees"],
                "test_case": [
                    {"input": "3\n1 2\n2 3\n", "output": "2\n"},
                    {"input": "1\n", "output": "0\n"},
                ],
                "correct_solution": [{"code": "int main() { return 0; }"}],
                "incorrect_solution": [{"code": "bad"}],
            }
        ],
    )

    examples = build_training_examples(
        audit_rows=[
            _audit_row(
                "p1",
                selected_template_name="Top-down Memoized DP",
                decision="accept",
                reward_reason="fully_certified",
            )
        ],
        source_jsonl=source_path,
    )

    assert len(examples) == 1
    example = examples[0]
    assert example["recipe_bucket"] == "recipe.dp.memo_default"
    assert example["is_success"] == 1
    assert example["is_fully_certified"] == 1
    assert example["description"] == "Count paths on a tree."
    assert example["tags"] == ["dp", "trees"]
    assert example["test_case_stats"]["num_tests"] == 2
    assert set(example["visible_context"].keys()) == {
        "problem_id",
        "description",
        "tags",
        "test_case_stats",
    }
    assert "correct_solution" not in example["visible_context"]
    assert "incorrect_solution" not in example["visible_context"]
    assert "correct_solution" not in json.dumps(example, ensure_ascii=False)
    assert "incorrect_solution" not in json.dumps(example, ensure_ascii=False)

    assert ONLINE_VISIBLE_SOURCE_FIELDS == ("description", "tags", "test_case")


def test_build_training_examples_raises_when_source_problem_is_missing(tmp_path: Path):
    source_path = tmp_path / "source.jsonl"
    _write_jsonl(source_path, [])

    with pytest.raises(ValueError, match="missing source rows"):
        build_training_examples(
            audit_rows=[_audit_row("missing_problem", selected_template_name="Top-down Memoized DP")],
            source_jsonl=source_path,
        )
