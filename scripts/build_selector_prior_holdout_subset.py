from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.oracle.selector_prior_holdout import (
    build_holdout_subset,
    load_problem_ids_from_jsonl,
    load_problem_ids_from_trusted_csv,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a non-overlapping selector prior holdout subset from a source JSONL."
    )
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--exclude-trusted-csv", default=None)
    parser.add_argument("--exclude-jsonl", action="append", default=[])
    parser.add_argument("--exclude-problem-id", action="append", default=[])
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=20)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    excluded_problem_ids = {problem_id for problem_id in args.exclude_problem_id if problem_id}
    if args.exclude_trusted_csv:
        excluded_problem_ids.update(load_problem_ids_from_trusted_csv(Path(args.exclude_trusted_csv)))
    for exclude_jsonl in args.exclude_jsonl:
        excluded_problem_ids.update(load_problem_ids_from_jsonl(Path(exclude_jsonl)))

    result = build_holdout_subset(
        dataset_path=Path(args.dataset),
        output_path=Path(args.output),
        excluded_problem_ids=excluded_problem_ids,
        offset=args.offset,
        limit=args.limit,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
