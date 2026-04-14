"""
Tag normalisation helpers.

We canonicalise tags so that planner / Q tags / role-inferred FunctionBlock
tags / skill-library tags can match reliably even if their original formats
use different casing or separators.
"""

from __future__ import annotations

import re
from typing import Iterable, Set


_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def canonicalize_tag(tag: str) -> str:
    """
    Convert an arbitrary tag string into a stable lowercase snake-ish form.

    Examples:
      "Quick_Sort" -> "quick_sort"
      "brute force" -> "brute_force"
      "DP" -> "dp"
    """
    if tag is None:
        return ""
    t = str(tag).strip().lower()
    t = t.replace(" ", "_")
    t = _NON_ALNUM.sub("_", t)
    t = re.sub(r"_+", "_", t)
    return t.strip("_")


def canonicalize_tag_set(tags: Iterable[str]) -> Set[str]:
    return {canonicalize_tag(t) for t in tags if str(t).strip()}


def jaccard_similarity_tags(tags_a: Iterable[str], tags_b: Iterable[str]) -> float:
    """
    Jaccard similarity on canonicalised tag sets.

    Empty vs empty returns 1.0 (no contradictory signal); if exactly one side is
    empty, returns 0.0.
    """
    a = canonicalize_tag_set(tags_a)
    b = canonicalize_tag_set(tags_b)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def canonicalize_text(text: str) -> str:
    """
    Canonicalise free-form text so substring matching works with
    canonicalised tags.
    """
    if text is None:
        return ""
    t = str(text).lower()
    t = _NON_ALNUM.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

