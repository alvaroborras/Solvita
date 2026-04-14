import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.nodes.abstract_problem import load_tag_whitelist, _filter_tags


def test_filter_tags_respects_whitelist():
    wl = ["greedy", "dp", "graphs"]
    assert _filter_tags(["Greedy", "unknown", "graphs"], wl) == ["greedy", "graphs"]


def test_load_tag_whitelist_reads_default_config():
    tags = load_tag_whitelist({})
    assert "greedy" in tags
    assert "dynamic_programming" in tags
