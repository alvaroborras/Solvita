import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.solver_network.planner_input import build_planner_input_from_state, canonical_text_for_similarity


def test_canonical_text_for_similarity_includes_objective():
    c = {"objective": "Minimize cost", "inputs": {"n": 5}}
    s = canonical_text_for_similarity(c)
    assert "Minimize cost" in s
    assert "inputs" in s


def test_build_planner_input_prefers_tags_selected_for_similarity_tags():
    st = {
        "problem": {
            "description": "raw",
            "tags_selected": ["graphs", "bfs"],
            "canonical": {"objective": "Reach t"},
        },
        "plan": {"algorithm_choice": "BFS"},
    }
    p = build_planner_input_from_state(st)
    assert "Reach t" in p.description
    assert p.similarity_tags == ["graphs", "bfs"]
    assert "graphs" in p.tags


def test_build_planner_input_falls_back_tags_from_algorithm_choice():
    st = {
        "problem": {"description": "x", "tags_selected": [], "canonical": {}},
        "plan": {"algorithm_choice": "binary search on answer"},
    }
    p = build_planner_input_from_state(st)
    assert "binary" in p.tags or "search" in p.tags
    assert p.similarity_tags
