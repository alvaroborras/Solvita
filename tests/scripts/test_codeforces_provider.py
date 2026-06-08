from __future__ import annotations

import json


def test_run_search_json_emits_codeforces_results(monkeypatch):
    import scripts.codeforces_provider as module

    class _CatalogStub:
        def search(self, query: str, limit: int):
            assert query == "1575 C"
            assert limit == 10
            return [
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

    monkeypatch.setattr(module, "build_catalog", lambda: _CatalogStub())

    output = module.run_search_json(query="1575 C", limit=10)
    payload = json.loads(output)

    assert payload == {
        "results": [
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
    }


def test_run_import_json_emits_problem_payload(monkeypatch):
    import scripts.codeforces_provider as module

    monkeypatch.setattr(
        module,
        "import_problem_json",
        lambda contest_id, index, url=None: {
            "problem_id": "codeforces_1575_C",
            "description": "Imported Codeforces problem",
            "public_tests": [],
            "_metadata": {"source": "codeforces"},
        },
    )

    output = module.run_import_json(contest_id=1575, index="C", url=None)
    payload = json.loads(output)

    assert payload == {
        "problem": {
            "problem_id": "codeforces_1575_C",
            "description": "Imported Codeforces problem",
            "public_tests": [],
            "_metadata": {"source": "codeforces"},
        }
    }
