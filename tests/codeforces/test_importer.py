from pathlib import Path

import pytest

import src.codeforces.importer as importer_module
from src.codeforces.importer import (
    build_problem_payload,
    fetch_problem_html,
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


def test_resolve_problem_key_accepts_codeforces_problemset_url():
    assert resolve_problem_key(
        contest_id=None,
        index=None,
        url="https://codeforces.com/problemset/problem/1575/C",
    ) == (1575, "C")


def test_resolve_problem_key_rejects_unsupported_url():
    with pytest.raises(ValueError, match="Unsupported Codeforces problem URL"):
        resolve_problem_key(
            contest_id=None,
            index=None,
            url="https://codeforces.com/gym/1575/problem/C",
        )


def test_parse_codeforces_problem_html_preserves_br_sample_line_breaks():
    parsed = parse_codeforces_problem_html(
        FIXTURE.read_text(encoding="utf-8"),
        contest_id=1575,
        index="C",
    )
    assert parsed["public_tests"] == [{"input": "1 3 2\n1", "output": "3"}]


def test_parse_codeforces_problem_html_returns_multiple_samples_in_order():
    html = """
<!DOCTYPE html>
<html lang="en">
  <body>
    <div class="problem-statement">
      <div class="header">
        <div class="title">C. Cyclic Sum</div>
      </div>
      <div class="sample-tests">
        <div class="sample-test">
          <div class="input">
            <div class="title">Input</div>
            <pre>1<br/>2 3</pre>
          </div>
          <div class="output">
            <div class="title">Output</div>
            <pre>5</pre>
          </div>
        </div>
        <div class="sample-test">
          <div class="input">
            <div class="title">Input</div>
            <pre>2<br/>5 8</pre>
          </div>
          <div class="output">
            <div class="title">Output</div>
            <pre>13</pre>
          </div>
        </div>
      </div>
    </div>
  </body>
</html>
"""

    parsed = parse_codeforces_problem_html(html, contest_id=1575, index="C")

    assert parsed["public_tests"] == [
        {"input": "1\n2 3", "output": "5"},
        {"input": "2\n5 8", "output": "13"},
    ]


@pytest.mark.parametrize(
    ("declared_charset", "body", "expected"),
    [
        ("iso-8859-1", "caf\xe9".encode("iso-8859-1"), "caf\xe9"),
        (None, "C. Cyclic Sum".encode("utf-8"), "C. Cyclic Sum"),
    ],
)
def test_fetch_problem_html_uses_declared_charset_with_utf8_fallback(
    monkeypatch,
    declared_charset: str | None,
    body: bytes,
    expected: str,
):
    class _Headers:
        def __init__(self, charset: str | None) -> None:
            self._charset = charset

        def get_content_charset(self) -> str | None:
            return self._charset

    class _Response:
        def __init__(self, payload: bytes, charset: str | None) -> None:
            self._payload = payload
            self.headers = _Headers(charset)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def read(self) -> bytes:
            return self._payload

    monkeypatch.setattr(
        importer_module.urllib.request,
        "urlopen",
        lambda request, timeout=30: _Response(body, declared_charset),
    )

    assert fetch_problem_html(1575, "C") == expected


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
