from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.oracle.oracle_memory_db import OracleMemoryDB  # noqa: E402
from src.oracle.oracle_memory_policy import load_training_examples_csv  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate a frozen Oracle memory DB snapshot on external holdout examples.")
    parser.add_argument("--data-dir", default="data/memory")
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--holdout-training-examples-csv", required=True)
    parser.add_argument("--output-dir", default="data/oracle_memory_models")
    parser.add_argument("--prefix", required=True)
    return parser


def _write_predictions_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "problem_id",
        "recipe_bucket",
        "selected_template_name",
        "decision",
        "reward_reason",
        "is_success",
        "is_fully_certified",
        "predicted_success_probability",
        "predicted_success_label",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    db = OracleMemoryDB.from_data_dir(Path(args.data_dir))
    db.initialize()
    holdout_examples = load_training_examples_csv(Path(args.holdout_training_examples_csv))
    evaluation = db.evaluate_holdout(args.snapshot_id, holdout_examples)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / f"{args.prefix}_holdout_summary.json"
    predictions_path = output_dir / f"{args.prefix}_holdout_predictions.csv"
    summary_path.write_text(json.dumps(evaluation, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    _write_predictions_csv(predictions_path, evaluation["prediction_rows"])

    print(json.dumps(evaluation, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
