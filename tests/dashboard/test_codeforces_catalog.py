from __future__ import annotations

import asyncio
from pathlib import Path

from dashboard.backend import server
from dashboard.backend.codeforces_catalog import (
    CodeforcesCatalog,
    normalize_problem_record,
)


def test_normalize_problem_record_builds_searchable_fields():
    record = normalize_problem_record(
        {
            "contestId": 1575,
            "index": "C",
            "name": "Cyclic Sum",
            "rating": 2100,
            "tags": ["math", "dp"],
        }
    )

    assert record["problem_id"] == "codeforces_1575_C"
    assert record["url"] == "https://codeforces.com/contest/1575/problem/C"
    assert record["name"] == "Cyclic Sum"


def test_catalog_search_matches_by_contest_index_and_keyword(tmp_path: Path):
    cache_path = tmp_path / "cache.json"
    catalog = CodeforcesCatalog(cache_path)
    catalog.save_cache(
        [
            {
                "contest_id": 1575,
                "index": "C",
                "name": "Cyclic Sum",
                "rating": 2100,
                "tags": ["math", "dp"],
                "url": "https://codeforces.com/contest/1575/problem/C",
                "problem_id": "codeforces_1575_C",
            },
            {
                "contest_id": 1873,
                "index": "A",
                "name": "Short Sort",
                "rating": 800,
                "tags": ["implementation"],
                "url": "https://codeforces.com/contest/1873/problem/A",
                "problem_id": "codeforces_1873_A",
            },
        ]
    )

    by_exact = catalog.search("1575 C", limit=5)
    by_name = catalog.search("cyclic", limit=5)

    assert [row["problem_id"] for row in by_exact] == ["codeforces_1575_C"]
    assert [row["problem_id"] for row in by_name] == ["codeforces_1575_C"]


def test_server_search_codeforces_returns_cached_results(monkeypatch, tmp_path: Path):
    cache_path = tmp_path / "cache.json"
    catalog = CodeforcesCatalog(cache_path)
    catalog.save_cache(
        [
            {
                "contest_id": 1575,
                "index": "C",
                "name": "Cyclic Sum",
                "rating": 2100,
                "tags": ["math", "dp"],
                "url": "https://codeforces.com/contest/1575/problem/C",
                "problem_id": "codeforces_1575_C",
            }
        ]
    )

    monkeypatch.setattr(server, "get_codeforces_catalog", lambda: catalog)

    response = asyncio.run(server.search_codeforces(q="cyclic", limit=10))

    assert response.cache_status == "ready"
    assert response.results[0].problem_id == "codeforces_1575_C"
