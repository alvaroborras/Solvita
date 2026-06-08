from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path
from typing import Any


CODEFORCES_PROBLEMSET_API = "https://codeforces.com/api/problemset.problems"
CODEFORCES_USER_AGENT = "AlgoPilot-Codeforces/1.0"


def normalize_problem_record(raw: dict[str, Any]) -> dict[str, Any]:
    contest_id = int(raw["contestId"])
    index = str(raw["index"]).strip().upper()
    return {
        "contest_id": contest_id,
        "index": index,
        "name": str(raw["name"]),
        "rating": int(raw["rating"]) if raw.get("rating") is not None else None,
        "tags": [str(tag) for tag in raw.get("tags", [])],
        "url": f"https://codeforces.com/contest/{contest_id}/problem/{index}",
        "problem_id": f"codeforces_{contest_id}_{index}",
    }


class CodeforcesCatalog:
    def __init__(self, cache_path: Path) -> None:
        self.cache_path = cache_path

    def load_cache(self) -> list[dict[str, Any]]:
        if not self.cache_path.exists():
            return []
        return json.loads(self.cache_path.read_text(encoding="utf-8"))

    def save_cache(self, rows: list[dict[str, Any]]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    def refresh_cache(self) -> list[dict[str, Any]]:
        request = urllib.request.Request(
            CODEFORCES_PROBLEMSET_API,
            headers={"User-Agent": CODEFORCES_USER_AGENT},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        rows = [
            normalize_problem_record(problem)
            for problem in payload["result"]["problems"]
            if problem.get("contestId") and problem.get("index")
        ]
        self.save_cache(rows)
        return rows

    def ensure_cache(self) -> list[dict[str, Any]]:
        rows = self.load_cache()
        return rows if rows else self.refresh_cache()

    def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        rows = self.ensure_cache()
        q = query.strip().lower()
        exact_match = re.match(r"^(\d+)\s*([a-z]\d?)$", q)
        if exact_match:
            contest_id = int(exact_match.group(1))
            index = exact_match.group(2).upper()
            return [
                row
                for row in rows
                if row["contest_id"] == contest_id and row["index"].upper() == index
            ][:limit]

        ranked = []
        for row in rows:
            haystack = " ".join(
                [
                    row["problem_id"].lower(),
                    row["name"].lower(),
                    row["index"].lower(),
                    " ".join(tag.lower() for tag in row["tags"]),
                ]
            )
            if q and q not in haystack:
                continue
            ranked.append(row)
        return ranked[:limit]
