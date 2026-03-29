import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.audit_selector_prior_features import build_source_context


def test_build_source_context_prefers_canonical_fields_and_preserves_raw_tags():
    source_row = {
        "id": "p1",
        "tags": ["raw_math", "raw_impl"],
        "problem_type": ["raw_type"],
        "key_elements": ["raw_key"],
        "objective": "raw objective",
        "graph_type": "raw_graph",
        "is_multi_solution": True,
        "data_structures": ["raw_ds"],
        "constraints": {"n": "10"},
        "description": "abcde",
        "public_tests": [{"input": "1", "output": "1"}, {"input": "2", "output": "2"}],
        "canonical": {
            "tags": ["canon_dp", "canon_math"],
            "problem_type": ["canonical_type"],
            "key_elements": ["canonical_key"],
            "objective": "canonical objective",
            "graph_type": "dag",
            "is_multi_solution": False,
            "data_structures": ["segment_tree"],
            "constraints": {"n": "100000"},
        },
    }

    context = build_source_context(source_row)

    assert context["problem_tags_joined"] == "raw_math|raw_impl"
    assert context["canonical_tags_joined"] == "canon_dp|canon_math"
    assert context["problem_type_joined"] == "canonical_type"
    assert context["key_elements_joined"] == "canonical_key"
    assert context["objective_text"] == "canonical objective"
    assert context["graph_type"] == "dag"
    assert context["is_multi_solution"] is False
    assert context["data_structures_joined"] == "segment_tree"
    assert context["constraints_json"] == json.dumps({"n": "100000"}, ensure_ascii=False, sort_keys=True)
    assert context["description_chars"] == 5
    assert context["public_tests_count"] == 2


def test_build_source_context_uses_raw_fields_when_canonical_is_missing():
    source_row = {
        "id": "p2",
        "problem_tags": ["graphs"],
        "problem_type": ["dynamic programming"],
        "key_elements": ["states", "transitions"],
        "objective_text": "Compute shortest transitions.",
        "graph_type": "dag",
        "is_multi_solution": False,
        "data_structures": ["graphs", "arrays"],
        "constraints": {"n": "200000"},
        "problem": "abcdef",
        "test_case": [{"input": "1", "output": "2"}],
    }

    context = build_source_context(source_row)

    assert context["problem_tags_joined"] == "graphs"
    assert context["canonical_tags_joined"] == "graphs"
    assert context["problem_type_joined"] == "dynamic programming"
    assert context["key_elements_joined"] == "states|transitions"
    assert context["objective_text"] == "Compute shortest transitions."
    assert context["graph_type"] == "dag"
    assert context["is_multi_solution"] is False
    assert context["data_structures_joined"] == "graphs|arrays"
    assert context["constraints_json"] == json.dumps({"n": "200000"}, ensure_ascii=False, sort_keys=True)
    assert context["description_chars"] == 6
    assert context["public_tests_count"] == 1


def test_audit_selector_prior_features_cli_help_runs():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "audit_selector_prior_features.py"

    result = subprocess.run(
        [sys.executable, str(script_path), "--help"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Audit selector prior richer feature availability" in result.stdout
