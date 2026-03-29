from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.oracle.selector_prior_holdout import run_selector_prior_external_holdout_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate frozen selector prior baselines on an external holdout cohort."
    )
    parser.add_argument("--dev-trusted-csv", required=True)
    parser.add_argument("--holdout-trusted-csv", required=True)
    parser.add_argument("--dev-model-json", required=True)
    parser.add_argument("--output-dir", default="data/selector_models")
    parser.add_argument("--prefix", default="selector_prior_holdout")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_selector_prior_external_holdout_pipeline(
        dev_trusted_csv=Path(args.dev_trusted_csv),
        holdout_trusted_csv=Path(args.holdout_trusted_csv),
        dev_model_json=Path(args.dev_model_json),
        output_dir=Path(args.output_dir),
        prefix=args.prefix,
    )
    print(json.dumps(result["evaluation"]["summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
