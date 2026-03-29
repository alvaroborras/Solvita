from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.oracle.oracle_memory_policy import (  # noqa: E402
    OracleMemoryFeatureConfig,
    train_oracle_memory_policy_pipeline,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train offline oracle memory / recipe confidence MVP.")
    parser.add_argument("--audit-csv", action="append", required=True)
    parser.add_argument("--source-jsonl", required=True)
    parser.add_argument("--output-dir", default="data/oracle_memory_models")
    parser.add_argument("--prefix", default="oracle_memory_policy")
    parser.add_argument("--min-bucket-examples", type=int, default=5)
    parser.add_argument("--description-vocab-cap", type=int, default=512)
    parser.add_argument("--description-min-token-frequency", type=int, default=1)
    parser.add_argument("--disable-action-interactions", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    feature_config = OracleMemoryFeatureConfig(
        description_vocab_cap=args.description_vocab_cap,
        description_min_token_frequency=args.description_min_token_frequency,
        include_action_interactions=not args.disable_action_interactions,
    )
    result = train_oracle_memory_policy_pipeline(
        audit_csv_paths=[Path(path) for path in args.audit_csv],
        source_jsonl=Path(args.source_jsonl),
        output_dir=Path(args.output_dir),
        prefix=args.prefix,
        min_bucket_examples=args.min_bucket_examples,
        feature_config=feature_config,
    )
    print(json.dumps(result["selection_summary"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
