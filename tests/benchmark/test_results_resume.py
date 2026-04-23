import json
from pathlib import Path

from src.benchmark.results_resume import (
    build_result_key,
    index_resumable_rows,
    normalize_result_rows,
    normalize_repeat_index,
)


def test_normalize_repeat_index_defaults_to_one():
    assert normalize_repeat_index(None) == 1
    assert normalize_repeat_index("bad") == 1
    assert normalize_repeat_index(0) == 1


def test_build_result_key_repeat_aware_uses_repeat_index():
    row = {"problem_id": "p1", "mode": "solvita_pipeline", "repeat_index": 2}
    assert build_result_key(row, repeat_aware=True) == ("p1", "solvita_pipeline", 2)
    assert build_result_key(row, repeat_aware=False) == ("p1", "solvita_pipeline")


def test_index_resumable_rows_uses_repeat_index_when_repeat_aware():
    rows = [
        {"problem_id": "p1", "mode": "solvita_pipeline", "repeat_index": 1, "status": "success"},
        {"problem_id": "p1", "mode": "solvita_pipeline", "repeat_index": 2, "status": "success"},
    ]
    index = index_resumable_rows(rows, modes=("solvita_pipeline",), repeat_aware=True)
    assert ("p1", "solvita_pipeline", 1) in index
    assert ("p1", "solvita_pipeline", 2) in index


def test_normalize_result_rows_prefers_last_row_on_key_collision():
    rows = [
        {"problem_id": "p1", "mode": "solvita_pipeline", "repeat_index": 1, "status": "success", "pass_rate": 0.1},
        {"problem_id": "p1", "mode": "solvita_pipeline", "repeat_index": 1, "status": "success", "pass_rate": 1.0},
    ]
    normalized = normalize_result_rows(rows, repeat_aware=True)
    assert len(normalized) == 1
    assert normalized[0]["pass_rate"] == 1.0
