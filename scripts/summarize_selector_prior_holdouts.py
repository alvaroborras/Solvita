from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.oracle.selector_prior_holdout_cumulative import run_selector_prior_holdout_cumulative_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Summarize multiple selector prior holdout prediction CSVs into cumulative artifacts."
    )
    parser.add_argument("--predictions-csv", action="append", required=True)
    parser.add_argument("--output-dir", default="data/selector_models")
    parser.add_argument("--prefix", default="selector_prior_holdout_cumulative")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_selector_prior_holdout_cumulative_pipeline(
        predictions_csv_paths=[Path(path) for path in args.predictions_csv],
        output_dir=Path(args.output_dir),
        prefix=args.prefix,
    )
    print(json.dumps(result["evaluation"]["summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
