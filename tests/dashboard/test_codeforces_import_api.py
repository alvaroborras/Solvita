from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from dashboard.backend import server
from dashboard.backend.models import CodeforcesImportRequest


FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "codeforces_problem_1575_C.html"
)


def test_parse_codeforces_problem_html_and_build_payload():
    from dashboard.backend.codeforces_import import (
        build_problem_payload,
        parse_codeforces_problem_html,
    )

    html = FIXTURE_PATH.read_text(encoding="utf-8")

    parsed = parse_codeforces_problem_html(html, 1575, "C")

    assert parsed["title"] == "C. Cyclic Sum"
    assert parsed["name"] == "Cyclic Sum"
    assert parsed["time_limit"] == "2 seconds"
    assert parsed["memory_limit"] == "256 megabytes"
    assert "Input" in parsed["description"]
    assert "Output" in parsed["description"]
    assert parsed["public_tests"] == [{"input": "1 3 2\n1", "output": "3"}]

    payload = build_problem_payload(
        parsed,
        contest_id=1575,
        index="C",
        rating=2100,
        tags=["math", "dp"],
    )

    assert payload["problem_id"] == "codeforces_1575_C"
    assert payload["_metadata"]["source"] == "codeforces"
    assert payload["_metadata"]["question_id"] == "codeforces_1575_C"
    assert payload["_metadata"]["cf_contest_id"] == 1575
    assert payload["_metadata"]["cf_index"] == "C"
    assert payload["public_tests"] == [{"input": "1 3 2\n1", "output": "3"}]


def test_import_codeforces_endpoint_writes_problem_file(
    monkeypatch, tmp_path: Path
):
    client = TestClient(server.app)
    written_payload = {
        "problem_id": "codeforces_1575_C",
        "description": "Imported from Codeforces",
        "public_tests": [{"input": "1 3 2\n1", "output": "3"}],
        "time_limit": 2000,
        "space_limit": 256,
        "_metadata": {
            "source": "codeforces",
            "question_id": "codeforces_1575_C",
            "cf_contest_id": 1575,
            "cf_index": "C",
        },
    }

    monkeypatch.setattr(server, "PROBLEMS_DIR", tmp_path)
    monkeypatch.setattr(
        server,
        "import_codeforces_problem_payload",
        lambda req: written_payload,
    )

    response = client.post(
        "/api/sources/codeforces/import",
        json=CodeforcesImportRequest(contest_id=1575, index="C").model_dump(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["problem_id"] == "codeforces_1575_C"
    assert body["filename"] == "codeforces_1575_C.json"
    assert body["problem"] == written_payload

    problem_path = tmp_path / "codeforces_1575_C.json"
    assert problem_path.exists()
    assert json.loads(problem_path.read_text(encoding="utf-8")) == written_payload
