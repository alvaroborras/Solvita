"""Skill selection prompts load from prompt_template.yaml."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.utils.prompt_templates import clear_prompt_template_cache
from src.solver_network.llm_skill_selection import (
    _skill_selection_system_prompt,
    build_minimal_skill_pick_prompt,
    build_skill_catalog_prompt,
)


def test_skill_selection_prompts_load_and_render():
    clear_prompt_template_cache()
    system_text = _skill_selection_system_prompt()
    assert "selected_skill_ids" in system_text
    assert "subproblem_dag" in system_text

    cands = [
        ("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "T", "desc", 0.5),
    ]
    u = build_skill_catalog_prompt(
        "sum array",
        cands,
        min_select=1,
        max_select=3,
        activated_graph_context="ctx",
        max_desc_chars=100,
    )
    assert "sum array" in u
    assert "ctx" in u
    assert "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" in u

    m = build_minimal_skill_pick_prompt(
        "x" * 10,
        cands,
        min_select=1,
        max_select=3,
        problem_max_chars=5,
    )
    assert "xxxxx" in m
    assert "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" in m
