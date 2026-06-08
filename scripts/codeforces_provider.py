#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from dashboard.backend.config import CODEFORCES_CACHE_PATH
from src.codeforces.catalog import CodeforcesCatalog
from src.codeforces.importer import (
    build_problem_payload,
    fetch_problem_html,
    parse_codeforces_problem_html,
    resolve_problem_key,
)


def build_catalog() -> CodeforcesCatalog:
    return CodeforcesCatalog(Path(CODEFORCES_CACHE_PATH))


def import_problem_json(
    contest_id: int | None,
    index: str | None,
    url: str | None = None,
) -> dict[str, Any]:
    resolved_contest_id, resolved_index = resolve_problem_key(
        contest_id=contest_id,
        index=index,
        url=url,
    )

    rating = None
    tags: list[str] = []
    try:
        rows = build_catalog().search(f"{resolved_contest_id} {resolved_index}", limit=1)
    except Exception:
        rows = []

    if rows:
        rating = rows[0].get("rating")
        tags = list(rows[0].get("tags", []))

    html = fetch_problem_html(resolved_contest_id, resolved_index)
    parsed = parse_codeforces_problem_html(html, resolved_contest_id, resolved_index)
    return build_problem_payload(
        parsed,
        contest_id=resolved_contest_id,
        index=resolved_index,
        rating=rating,
        tags=tags,
    )


def run_search_json(*, query: str, limit: int) -> str:
    rows = build_catalog().search(query, limit)
    return json.dumps({"results": rows}, ensure_ascii=False)


def run_import_json(
    *,
    contest_id: int | None,
    index: str | None,
    url: str | None,
) -> str:
    payload = import_problem_json(contest_id, index, url=url)
    return json.dumps({"problem": payload}, ensure_ascii=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Codeforces provider bridge for AlgoPilot CLI"
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    search_parser = subcommands.add_parser("search")
    search_parser.add_argument("--query", required=True)
    search_parser.add_argument("--limit", type=int, default=10)

    import_parser = subcommands.add_parser("import")
    import_parser.add_argument("--contest-id", type=int)
    import_parser.add_argument("--index")
    import_parser.add_argument("--url")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "search":
        sys.stdout.write(run_search_json(query=args.query, limit=args.limit))
        return
    if args.command == "import":
        sys.stdout.write(
            run_import_json(
                contest_id=args.contest_id,
                index=args.index,
                url=args.url,
            )
        )
        return
    raise SystemExit(2)


if __name__ == "__main__":
    main()
