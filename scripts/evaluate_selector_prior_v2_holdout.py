from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.oracle.selector_prior_v2 import run_selector_prior_v2_holdout_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate frozen selector prior v2 on external holdouts.")
    parser.add_argument("--dev-trusted-csv", required=True)
    parser.add_argument("--v2-model-json", required=True)
    parser.add_argument("--holdout-trusted-csv", action="append", required=True)
    parser.add_argument("--canonical-v1-dev-trusted-csv", required=True)
    parser.add_argument("--canonical-v1-model-json", required=True)
    parser.add_argument("--output-dir", default="data/selector_models")
    parser.add_argument("--prefix", default="selector_prior_v2_pilots")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_selector_prior_v2_holdout_pipeline(
        dev_trusted_csv=Path(args.dev_trusted_csv),
        v2_model_json=Path(args.v2_model_json),
        holdout_trusted_csvs=[Path(path) for path in args.holdout_trusted_csv],
        canonical_v1_dev_trusted_csv=Path(args.canonical_v1_dev_trusted_csv),
        canonical_v1_model_json=Path(args.canonical_v1_model_json),
        output_dir=Path(args.output_dir),
        prefix=args.prefix,
    )
    print(json.dumps(result["cumulative"]["summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
