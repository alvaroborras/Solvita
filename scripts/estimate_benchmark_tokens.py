#!/usr/bin/env python3
"""Best-effort token backfill for existing benchmark results.

This script is intentionally conservative:
- for rows that already contain `prompt_tokens` / `completion_tokens`, it preserves them
- for historical rows, it estimates token counts from the best available artifacts
- it emits notes so downstream accounting can distinguish exact logging from backfill
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
import sys
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.benchmark.modes.single_pass import build_single_pass_prompt
from src.llm.token_usage import (
    estimate_message_tokens,
    estimate_text_tokens,
    estimate_tokens_from_chars,
)


PROMPT_CHAR_RE = re.compile(r"\[PROMPT:[^\]]+\]\s+total_chars=(\d+)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Estimate prompt/completion tokens for benchmark rows.")
    parser.add_argument("--results-jsonl", required=True, type=Path)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--generated-root", type=Path, default=Path("data/generated"))
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def load_jsonl(path: Path) -> list[Dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_manifest_map(path: Path | None) -> Dict[str, Dict[str, Any]]:
    if path is None or not path.exists():
        return {}
    return {
        row["problem_id"]: row
        for row in load_jsonl(path)
        if isinstance(row, dict) and row.get("problem_id")
    }


def safe_problem_dir_name(problem_id: str) -> str:
    match = re.match(r"^(\d+_[A-Z])", problem_id)
    if match:
        return match.group(1)
    return re.sub(r"[^A-Za-z0-9_-]+", "_", problem_id).strip("_") or "unknown"


def estimate_single_pass_tokens(
    row: Dict[str, Any],
    manifest_row: Dict[str, Any] | None,
    results_dir: Path,
) -> Dict[str, Any]:
    notes: list[str] = []
    prompt_tokens = row.get("prompt_tokens")
    completion_tokens = row.get("completion_tokens")

    if prompt_tokens is None and manifest_row:
        payload_path = Path(manifest_row["problem_payload_path"])
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        prompt = build_single_pass_prompt(payload.get("raw_problem", {}))
        prompt_tokens = estimate_message_tokens(
            [{"role": "user", "content": prompt}],
            model="gpt-5.4",
        )
        notes.append("prompt estimated from reconstructed single-pass prompt")
    elif prompt_tokens is None:
        notes.append("prompt unavailable: manifest not provided")

    if completion_tokens is None:
        artifact_dir = results_dir / "artifacts" / "single_pass"
        stem = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in row["problem_id"]).strip("._") or "unknown"
        raw_path = artifact_dir / f"{stem}.raw.txt"
        if raw_path.exists():
            completion_tokens = estimate_text_tokens(raw_path.read_text(encoding="utf-8"), model="gpt-5.4")
            notes.append("completion estimated from saved single-pass raw response")
        elif (row.get("error") or "") == "Empty model response":
            completion_tokens = 0
            notes.append("completion estimated as zero from empty response error")
        else:
            notes.append("completion unavailable: no saved single-pass raw response")

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "token_usage_source": "estimated",
        "token_estimation_notes": notes,
    }


def estimate_pipeline_tokens(
    row: Dict[str, Any],
    generated_root: Path,
) -> Dict[str, Any]:
    notes: list[str] = []
    prompt_tokens = row.get("prompt_tokens")
    completion_tokens = row.get("completion_tokens")

    workflow_log_path = row.get("workflow_log_path")
    if prompt_tokens is None and workflow_log_path:
        log_path = Path(workflow_log_path)
        if log_path.exists():
            log_text = log_path.read_text(encoding="utf-8", errors="ignore")
            prompt_chars = sum(int(match.group(1)) for match in PROMPT_CHAR_RE.finditer(log_text))
            prompt_tokens = estimate_tokens_from_chars(prompt_chars)
            notes.append("prompt estimated from workflow log prompt char totals")
        else:
            notes.append("prompt unavailable: workflow log missing")
    elif prompt_tokens is None:
        notes.append("prompt unavailable: workflow log path missing")

    if completion_tokens is None:
        generated_dir = generated_root / safe_problem_dir_name(str(row["problem_id"]))
        raw_files = sorted((generated_dir / "code").glob("*_raw.txt"))
        if raw_files:
            completion_tokens = sum(
                estimate_text_tokens(raw_file.read_text(encoding="utf-8", errors="ignore"))
                for raw_file in raw_files
            )
            notes.append("completion estimated from saved pipeline raw response files")
        else:
            notes.append("completion unavailable: no saved pipeline raw response files")

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "token_usage_source": "estimated",
        "token_estimation_notes": notes,
    }


def estimate_row(
    row: Dict[str, Any],
    manifest_map: Dict[str, Dict[str, Any]],
    results_dir: Path,
    generated_root: Path,
) -> Dict[str, Any]:
    augmented = dict(row)

    prompt_tokens = row.get("prompt_tokens")
    completion_tokens = row.get("completion_tokens")
    if isinstance(prompt_tokens, int) and isinstance(completion_tokens, int) and (
        prompt_tokens > 0 or completion_tokens > 0
    ):
        augmented.setdefault("token_estimation_notes", ["used logged token fields"])
        return augmented

    manifest_row = manifest_map.get(str(row.get("problem_id")))
    if row.get("mode") in ("single_pass", "gpt52_single_pass"):
        estimate = estimate_single_pass_tokens(row, manifest_row, results_dir)
    else:
        estimate = estimate_pipeline_tokens(row, generated_root)

    augmented.update(estimate)
    return augmented


def main() -> None:
    args = parse_args()
    results_path = args.results_jsonl
    results_dir = results_path.parent
    output_path = args.output or results_path.with_name(f"{results_path.stem}.with_token_estimates.jsonl")

    rows = load_jsonl(results_path)
    manifest_map = load_manifest_map(args.manifest)
    augmented_rows = [
        estimate_row(
            row=row,
            manifest_map=manifest_map,
            results_dir=results_dir,
            generated_root=args.generated_root,
        )
        for row in rows
    ]

    output_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in augmented_rows) + "\n",
        encoding="utf-8",
    )
    print(output_path)


if __name__ == "__main__":
    main()
