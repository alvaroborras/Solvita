from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.oracle.selector_prior import train_selector_prior_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train and evaluate offline selector prior baseline.")
    parser.add_argument("--input-csv", required=True, help="Trusted selector dataset CSV")
    parser.add_argument("--output-dir", default="data/selector_models")
    parser.add_argument("--prefix", default="selector_prior_baseline")
    parser.add_argument("--cohort-priority", default="selected_family,rerun,unknown")
    parser.add_argument("--eval-protocol", default="leave_one_problem_out")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cohort_priority = tuple(
        item.strip() for item in args.cohort_priority.split(",") if item.strip()
    )
    result = train_selector_prior_pipeline(
        input_csv=Path(args.input_csv),
        output_dir=Path(args.output_dir),
        prefix=args.prefix,
        cohort_priority=cohort_priority,
        eval_protocol=args.eval_protocol,
    )
    print(json.dumps(result["evaluation"]["summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
