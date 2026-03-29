from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.oracle.selector_prior_diagnostics import run_selector_prior_diagnostics_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare offline selector prior model against weak and rule baselines."
    )
    parser.add_argument("--input-csv", required=True, help="Trusted selector dataset CSV")
    parser.add_argument("--output-dir", default="data/selector_models")
    parser.add_argument("--prefix", default="selector_prior_baseline_diagnosis")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_selector_prior_diagnostics_pipeline(
        input_csv=Path(args.input_csv),
        output_dir=Path(args.output_dir),
        prefix=args.prefix,
    )
    print(json.dumps(result["diagnosis"]["summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
