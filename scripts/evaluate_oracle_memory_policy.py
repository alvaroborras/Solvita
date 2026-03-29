from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.oracle.oracle_memory_policy import evaluate_oracle_memory_policy_pipeline  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate frozen oracle memory / recipe confidence MVP.")
    parser.add_argument("--training-examples-csv", required=True)
    parser.add_argument("--model-json", required=True)
    parser.add_argument("--output-dir", default="data/oracle_memory_models")
    parser.add_argument("--prefix", default="oracle_memory_policy")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = evaluate_oracle_memory_policy_pipeline(
        training_examples_csv=Path(args.training_examples_csv),
        model_json=Path(args.model_json),
        output_dir=Path(args.output_dir),
        prefix=args.prefix,
    )
    print(json.dumps(result["summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
