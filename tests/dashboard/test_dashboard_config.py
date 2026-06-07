from __future__ import annotations

from pathlib import Path

from dashboard.backend.config import load_settings
from dashboard.backend.models import (
    CodeforcesImportRequest,
    CodeforcesImportResponse,
    CodeforcesSearchResponse,
    CodeforcesSearchResult,
)

def test_load_settings_exposes_codeforces_cache_path(tmp_path: Path):
    project_root = tmp_path / "repo"
    backend_dir = project_root / "dashboard" / "backend"
    backend_dir.mkdir(parents=True)
    cache_path = tmp_path / "cf-cache.json"

    settings = load_settings(
        env={"ALGOPILOT_CODEFORCES_CACHE_PATH": str(cache_path)},
        base_file=backend_dir / "config.py",
        current_python="/usr/bin/python3",
    )

    assert settings.codeforces_cache_path == cache_path


def test_codeforces_models_accept_contest_index_and_url_forms():
    result = CodeforcesSearchResult(
        contest_id=1575,
        index="C",
        name="Cyclic Sum",
        rating=2100,
        tags=["math", "dp"],
        url="https://codeforces.com/contest/1575/problem/C",
        problem_id="codeforces_1575_C",
    )
    response = CodeforcesSearchResponse(results=[result], cache_status="ready")

    by_key = CodeforcesImportRequest(contest_id=1575, index="C")
    by_url = CodeforcesImportRequest(url="https://codeforces.com/contest/1575/problem/C")

    assert response.results[0].problem_id == "codeforces_1575_C"
    assert by_key.contest_id == 1575
    assert by_key.index == "C"
    assert by_url.url.endswith("/1575/problem/C")
    assert not hasattr(by_key, "uses_key")


def test_codeforces_import_response_preserves_payload():
    response = CodeforcesImportResponse(
        problem_id="codeforces_1575_C",
        filename="codeforces_1575_C.json",
        problem={
            "name": "Cyclic Sum",
            "source": "codeforces",
            "url": "https://codeforces.com/contest/1575/problem/C",
        },
    )

    assert response.problem_id == "codeforces_1575_C"
    assert response.filename == "codeforces_1575_C.json"
    assert response.problem["source"] == "codeforces"
