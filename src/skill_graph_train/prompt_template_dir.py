"""Resolved paths to ``skill_graph_train/prompt_template`` (logic_chain / logic_diff templates)."""

from __future__ import annotations

from pathlib import Path

# skill_graph_train/src/skill_graph_train/ → repo root skill_graph_train/
_REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPT_TEMPLATE_DIR = _REPO_ROOT / "prompt_template"
LOGIC_CHAIN_TEMPLATE = PROMPT_TEMPLATE_DIR / "correct_solution_logic_chain.txt"
LOGIC_DIFF_TEMPLATE = PROMPT_TEMPLATE_DIR / "correct_vs_incorrect_logic_diff.txt"
