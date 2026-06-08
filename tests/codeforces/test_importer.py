from pathlib import Path

import pytest

from src.codeforces.importer import (
    build_problem_payload,
    parse_codeforces_problem_html,
    resolve_problem_key,
)


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "codeforces_problem_1575_C.html"


def test_resolve_problem_key_accepts_contest_and_index():
    assert resolve_problem_key(contest_id=1575, index="c", url=None) == (1575, "C")


def test_resolve_problem_key_accepts_codeforces_problem_url():
    assert resolve_problem_key(
        contest_id=None,
        index=None,
        url="https://codeforces.com/contest/1575/problem/C",
    ) == (1575, "C")


def test_resolve_problem_key_rejects_unsupported_url():
    with pytest.raises(ValueError, match="Unsupported Codeforces problem URL"):
        resolve_problem_key(
            contest_id=None,
            index=None,
            url="https://codeforces.com/problemset/problem/1575/C",
        )


def test_parse_codeforces_problem_html_preserves_br_sample_line_breaks():
    parsed = parse_codeforces_problem_html(
        FIXTURE.read_text(encoding="utf-8"),
        contest_id=1575,
        index="C",
    )
    assert parsed["public_tests"] == [{"input": "1 3 2\n1", "output": "3"}]


def test_build_problem_payload_produces_shared_local_problem_shape():
    parsed = parse_codeforces_problem_html(
        FIXTURE.read_text(encoding="utf-8"),
        contest_id=1575,
        index="C",
    )
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
