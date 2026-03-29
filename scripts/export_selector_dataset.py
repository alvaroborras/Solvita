from __future__ import annotations

import argparse
from pathlib import Path

from src.oracle.selector_dataset_export import export_selector_dataset


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export selector dataset audit and trusted subsets.")
    parser.add_argument("--input", action="append", required=True, help="Path to oracle_candidate_records.jsonl")
    parser.add_argument(
        "--problem-source",
        default=None,
        help="Optional single problem-source JSONL file used to join problem context.",
    )
    parser.add_argument("--output-dir", default="data/selector_datasets")
    parser.add_argument("--prefix", default="selector_dataset")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    export_selector_dataset(
        input_paths=[Path(path) for path in args.input],
        problem_source_path=Path(args.problem_source) if args.problem_source else None,
        output_dir=Path(args.output_dir),
        prefix=args.prefix,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
