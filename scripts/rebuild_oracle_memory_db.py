from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.oracle.oracle_memory_db import OracleMemoryDB
from src.oracle.oracle_memory_policy import (
    write_feature_weights_csv,
    write_oof_predictions_csv,
    write_summary_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild oracle memory DB action stats and model snapshots.")
    parser.add_argument("--data-dir", type=Path, default=Path("data/memory"))
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("data/oracle_memory_models"))
    parser.add_argument("--prefix", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db = OracleMemoryDB.from_data_dir(args.data_dir)
    db.initialize()
    rebuild_result = db.rebuild(snapshot_id=args.snapshot_id)

    write_summary_json(
        summary=rebuild_result["selection_summary"],
        output_dir=args.output_dir,
        prefix=args.prefix,
        suffix="selection_summary",
    )
    write_summary_json(
        summary=rebuild_result["recipe_bucket_summary"],
        output_dir=args.output_dir,
        prefix=args.prefix,
        suffix="recipe_bucket_summary",
    )
    write_feature_weights_csv(
        model=rebuild_result["model"],
        output_dir=args.output_dir,
        prefix=args.prefix,
    )
    write_oof_predictions_csv(
        prediction_rows=rebuild_result["oof_predictions"],
        output_dir=args.output_dir,
        prefix=args.prefix,
    )

    print(
        json.dumps(
            {
                "snapshot_id": rebuild_result["snapshot_id"],
                "num_observations": rebuild_result["num_observations"],
                "output_dir": str(args.output_dir),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
