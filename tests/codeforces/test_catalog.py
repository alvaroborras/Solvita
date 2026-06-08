from pathlib import Path

from src.codeforces.catalog import CodeforcesCatalog, normalize_problem_record


def test_normalize_problem_record_builds_shared_problem_fields():
    row = normalize_problem_record(
        {
            "contestId": 1575,
            "index": "C",
            "name": "Cyclic Sum",
            "rating": 2100,
            "tags": ["math", "dp"],
        }
    )

    assert row["problem_id"] == "codeforces_1575_C"
    assert row["url"] == "https://codeforces.com/contest/1575/problem/C"
    assert row["name"] == "Cyclic Sum"


def test_codeforces_catalog_search_matches_by_problem_id_keyword(tmp_path: Path):
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

    upper = catalog.search("codeforces_1575_C", limit=5)
    lower = catalog.search("codeforces_1575_c", limit=5)

    assert [row["problem_id"] for row in upper] == ["codeforces_1575_C"]
    assert [row["problem_id"] for row in lower] == ["codeforces_1575_C"]
