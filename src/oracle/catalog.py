from __future__ import annotations

from typing import Any, Dict

from src.memory.seeds.oracle_items import ORACLE_SEED_ITEMS


def build_oracle_catalog() -> Dict[str, Dict[str, Any]]:
    catalog: Dict[str, Dict[str, Any]] = {}
    for item in ORACLE_SEED_ITEMS:
        family_id = item["family_id"]
        catalog[family_id] = item
    return catalog
