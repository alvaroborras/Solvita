import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.nodes.abstract_problem import (
    TagWhitelistBundle,
    load_tag_whitelist,
    _filter_tags,
    _parse_algorithmic_tags_from_llm,
)


def test_filter_tags_respects_whitelist():
    wl = ["greedy", "dp", "graphs"]
    assert _filter_tags(["Greedy", "unknown", "graphs"], wl) == ["greedy", "graphs"]


def test_filter_tags_normalizes_hyphens():
    wl = ["binary_search", "two_pointers"]
    assert _filter_tags(["Binary-Search", "two-pointers"], wl) == ["binary_search", "two_pointers"]


def test_parse_tags_prefers_level1_level2_keys():
    bundle = TagWhitelistBundle(
        merged=["dp", "digit_dp"],
        tags_level1=["dp"],
        tags_level2=["digit_dp"],
    )
    l1, l2 = _parse_algorithmic_tags_from_llm(
        {"algorithmic_tags_level1": ["DP"], "algorithmic_tags_level2": ["digit_dp", "unknown"]},
        bundle,
    )
    assert l1 == ["dp"]
    assert l2 == ["digit_dp"]


def test_parse_tags_legacy_splits_by_whitelist():
    bundle = TagWhitelistBundle(
        merged=["greedy", "digit_dp"],
        tags_level1=["greedy"],
        tags_level2=["digit_dp"],
    )
    l1, l2 = _parse_algorithmic_tags_from_llm(
        {"algorithmic_tags": ["Greedy", "digit_dp", "nope"]},
        bundle,
    )
    assert l1 == ["greedy"]
    assert l2 == ["digit_dp"]


def test_load_tag_whitelist_reads_default_config():
    tags = load_tag_whitelist({})
    assert "greedy" in tags
    assert "dp" in tags
    assert "graphs" in tags
    assert "0_1_bfs" in tags
