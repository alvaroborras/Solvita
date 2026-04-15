#!/usr/bin/env python3
"""Run benchmark modes on a normalized manifest."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.benchmark.dataset import load_benchmark_manifest
from src.benchmark.modes.gpt52_single_pass import run_gpt52_single_pass_case
from src.benchmark.modes.pipeline import run_pipeline_benchmark_case
from src.benchmark.reporting import write_summary_outputs


MODE_RUNNERS = {
    "solvita_pipeline": run_pipeline_benchmark_case,
    "gpt52_single_pass": run_gpt52_single_pass_case,
}

BENCH_TO_MANIFEST_NAME = {
    "code-contest": "code-contest.jsonl",
    "apps": "apps.jsonl",
    "aethercode": "aethercode.jsonl",
}

BENCH_TO_HF_SOURCE = {
    "code-contest": {"dataset": "deepmind/code_contests", "split": "test"},
    "apps": {"dataset": "codeparrot/apps", "split": "test"},
    "aethercode": {"dataset": "m-a-p/AetherCode", "name": "v1_2024", "split": "test"},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run benchmark modes on a frozen manifest.")
    parser.add_argument("--manifest", required=False, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--modes",
        nargs="+",
        default=["solvita_pipeline", "gpt52_single_pass"],
        choices=sorted(MODE_RUNNERS.keys()),
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--config-path", type=str, default="config/models.yaml")
    parser.add_argument(
        "--max-workers",
        type=int,
        default=1,
        help="Number of problems to run in parallel. Uses separate worker processes.",
    )
    parser.add_argument(
        "--bench",
        choices=["code-contest", "apps", "aethercode", "all"],
        default=None,
        help=(
            "Benchmark preset. When set, manifests are loaded from --bench-root "
            "(e.g. code-contest.jsonl, apps.jsonl, aethercode.jsonl). "
            "Use 'all' to run all three in one command."
        ),
    )
    parser.add_argument(
        "--bench-root",
        type=Path,
        default=Path("benchmark/manifests"),
        help="Directory for local benchmark caches/artifacts.",
    )
    return parser.parse_args()


def load_problem_payload(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_problem_modes(
    item: Any,
    modes: List[str],
    config: Dict[str, Any],
) -> List[Dict[str, Any]]:
    payload = load_problem_payload(item.problem_payload_path)
    rows: List[Dict[str, Any]] = []

    for mode in modes:
        runner = MODE_RUNNERS[mode]
        try:
            result = runner(problem_payload=payload, config=config)
            row = {
                "problem_id": result.problem_id,
                "mode": result.mode,
                "status": result.status,
                "compile_success": result.compile_success,
                "passed_tests": result.passed_tests,
                "total_tests": result.total_tests,
                "pass_rate": result.pass_rate,
                "elapsed_total_s": result.elapsed_total_s,
                "llm_infer_s": result.llm_infer_s,
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "token_usage_source": result.token_usage_source,
                "error": result.error,
                "hack_result": result.hack_result,
                "hack_passed": result.hack_passed,
                "generator_failure_kind": result.generator_failure_kind,
                "generator_failure_reason": result.generator_failure_reason,
                "workflow_log_path": result.workflow_log_path,
            }
        except Exception as exc:
            row = {
                "problem_id": item.problem_id,
                "mode": mode,
                "status": "error",
                "compile_success": False,
                "passed_tests": 0,
                "total_tests": 0,
                "pass_rate": 0.0,
                "elapsed_total_s": 0.0,
                "llm_infer_s": 0.0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "token_usage_source": None,
                "error": str(exc),
                "hack_result": None,
                "hack_passed": None,
                "generator_failure_kind": None,
                "generator_failure_reason": None,
                "workflow_log_path": None,
            }
        rows.append(row)

    return rows


def _run_single_manifest(
    *,
    manifest: Path,
    output_dir: Path,
    modes: List[str],
    config_path: str,
    max_workers: int,
    limit: int | None = None,
) -> Dict[str, Any]:
    items = load_benchmark_manifest(manifest)
    if limit is not None:
        items = items[:limit]
    output_dir.mkdir(parents=True, exist_ok=True)
    results_path = output_dir / "results.jsonl"

    config = {
        "config_path": config_path,
        "benchmark_output_dir": str(output_dir),
    }
    rows: List[Dict[str, Any]] = []
    worker_count = max(1, int(max_workers))

    with results_path.open("w", encoding="utf-8") as fh:
        if worker_count == 1 or len(items) <= 1:
            for item in items:
                for row in _run_problem_modes(item, modes, config):
                    rows.append(row)
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                    fh.flush()
        else:
            worker_count = min(worker_count, len(items), os.cpu_count() or worker_count)
            with ProcessPoolExecutor(max_workers=worker_count) as executor:
                future_to_problem = {
                    executor.submit(_run_problem_modes, item, modes, config): item.problem_id
                    for item in items
                }
                for future in as_completed(future_to_problem):
                    for row in future.result():
                        rows.append(row)
                        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                        fh.flush()

    summary = write_summary_outputs(output_dir, rows)
    return {
        "manifest": str(manifest),
        "output_dir": str(output_dir),
        "rows": len(rows),
        "summary": summary,
    }


def _resolve_bench_targets(bench: str, bench_root: Path) -> List[tuple[str, Path]]:
    if bench == "all":
        names = ["code-contest", "apps", "aethercode"]
    else:
        names = [bench]
    return [(name, bench_root / BENCH_TO_MANIFEST_NAME[name]) for name in names]


def _normalize_tests(test_group: Any) -> List[Dict[str, str]]:
    if not isinstance(test_group, dict):
        return []
    inputs = list((test_group or {}).get("input", []) or [])
    outputs = list((test_group or {}).get("output", []) or [])
    return [{"input": inp, "output": out} for inp, out in zip(inputs, outputs)]


def _coerce_to_test_pairs(inputs: Any, outputs: Any) -> List[Dict[str, str]]:
    in_list = list(inputs or []) if isinstance(inputs, list) else []
    out_list = list(outputs or []) if isinstance(outputs, list) else []
    return [{"input": str(inp), "output": str(out)} for inp, out in zip(in_list, out_list)]


def _extract_tests_generic(row: Dict[str, Any]) -> List[Dict[str, str]]:
    # Common fields seen in APPS-like datasets.
    io_blob = row.get("input_output")
    if isinstance(io_blob, str):
        try:
            io_blob = json.loads(io_blob)
        except Exception:
            io_blob = None
    if isinstance(io_blob, dict):
        for in_key, out_key in (("inputs", "outputs"), ("input", "output")):
            pairs = _coerce_to_test_pairs(io_blob.get(in_key), io_blob.get(out_key))
            if pairs:
                return pairs

    # AetherCode-like variants.
    for container_key in ("test_cases", "tests", "official_tests", "private_tests"):
        container = row.get(container_key)
        if isinstance(container, dict):
            pairs = _coerce_to_test_pairs(container.get("input"), container.get("output"))
            if pairs:
                return pairs
        if isinstance(container, list):
            pairs = []
            for item in container:
                if not isinstance(item, dict):
                    continue
                inp = item.get("input")
                out = item.get("output")
                if inp is None or out is None:
                    continue
                pairs.append({"input": str(inp), "output": str(out)})
            if pairs:
                return pairs
    return []


def _build_problem_id(bench: str, row: Dict[str, Any], idx: int) -> str:
    for key in ("problem_id", "id", "task_id", "name"):
        value = row.get(key)
        if value:
            return str(value)
    return f"{bench}_{idx:06d}_{uuid4().hex[:8]}"


def _build_raw_problem(bench: str, row: Dict[str, Any], public_tests: List[Dict[str, str]]) -> Dict[str, Any]:
    description = (
        row.get("description")
        or row.get("question")
        or row.get("problem")
        or row.get("statement")
        or ""
    )
    time_limit = row.get("time_limit") or row.get("time_limit_ms")
    space_limit = row.get("space_limit") or row.get("memory_limit") or row.get("memory_limit_mb")
    return {
        "description": str(description),
        "time_limit": int(time_limit) if isinstance(time_limit, (int, float)) else 2000,
        "space_limit": int(space_limit) if isinstance(space_limit, (int, float)) else 256,
        "public_tests": public_tests,
        "_metadata": {
            "benchmark_source": bench,
            "dataset": BENCH_TO_HF_SOURCE[bench]["dataset"],
        },
    }


def _build_payloads_from_hf(bench_name: str, limit: int | None) -> List[Dict[str, Any]]:
    source = BENCH_TO_HF_SOURCE[bench_name]
    if bench_name == "apps":
        try:
            from huggingface_hub import hf_hub_download
        except ImportError as exc:
            raise SystemExit("Missing dependency 'huggingface_hub'. Install it to use --bench apps.") from exc
        test_path = hf_hub_download(
            repo_id=source["dataset"],
            filename="test.jsonl",
            repo_type="dataset",
        )

        def _apps_rows():
            with Path(test_path).open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue

        rows_iter = _apps_rows()
    else:
        try:
            from datasets import load_dataset
        except ImportError as exc:
            raise SystemExit("Missing dependency 'datasets'. Install it to use --bench mode.") from exc
        load_kwargs: Dict[str, Any] = {"split": source["split"], "streaming": True}
        if "name" in source:
            load_kwargs["name"] = source["name"]
        rows_iter = load_dataset(source["dataset"], **load_kwargs)

    payloads: List[Dict[str, Any]] = []
    for idx, row in enumerate(rows_iter):
        if not isinstance(row, dict):
            continue
        if bench_name == "code-contest":
            public_tests = _normalize_tests(row.get("public_tests", {}))
            private_tests = _normalize_tests(row.get("private_tests", {}))
            generated_tests = _normalize_tests(row.get("generated_tests", {}))
            official_tests = private_tests + generated_tests
        else:
            public_tests = []
            official_tests = _extract_tests_generic(row)

        if not official_tests:
            continue

        problem_id = _build_problem_id(bench_name, row, idx)
        payloads.append(
            {
                "problem_id": problem_id,
                "source": str(row.get("source", bench_name)),
                "difficulty": str(row.get("difficulty", "unknown")),
                "benchmark_version": f"hf-{bench_name}",
                "raw_problem": _build_raw_problem(bench_name, row, public_tests),
                "official_tests": official_tests,
                "dataset_meta": {
                    "dataset_name": source["dataset"],
                    "split": source["split"],
                    "title": row.get("name") or row.get("title") or problem_id,
                },
            }
        )

        if limit is not None and len(payloads) >= limit:
            break

    if not payloads:
        raise SystemExit(f"No valid benchmark items extracted from HF dataset for '{bench_name}'.")
    return payloads


def _write_bench_payload_manifest(
    *,
    bench_name: str,
    payloads: List[Dict[str, Any]],
    bench_root: Path,
) -> Path:
    cache_root = (bench_root / ".hf_payload_cache" / bench_name).resolve()
    payload_dir = cache_root / "payloads"
    payload_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = cache_root / "manifest.jsonl"

    with manifest_path.open("w", encoding="utf-8") as fh:
        for payload in payloads:
            payload_path = payload_dir / f"{payload['problem_id']}.json"
            payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            row = {
                "problem_id": payload["problem_id"],
                "source": payload["source"],
                "difficulty": payload["difficulty"],
                "dataset_name": payload["dataset_meta"]["dataset_name"],
                "split": payload["dataset_meta"]["split"],
                "has_full_tests": True,
                "problem_payload_path": str(payload_path),
                "benchmark_version": payload["benchmark_version"],
                "time_limit": payload["raw_problem"].get("time_limit"),
                "memory_limit": payload["raw_problem"].get("space_limit"),
                "tags": [],
                "title": payload["dataset_meta"].get("title"),
                "language": "cpp",
                "notes": {},
            }
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return manifest_path


def main() -> None:
    args = parse_args()
    if args.bench is None and args.manifest is None:
        raise SystemExit("Either --manifest or --bench must be provided.")

    if args.bench is None:
        _run_single_manifest(
            manifest=args.manifest,
            output_dir=args.output_dir,
            modes=args.modes,
            config_path=args.config_path,
            max_workers=args.max_workers,
            limit=args.limit,
        )
        return

    args.output_dir.mkdir(parents=True, exist_ok=True)
    suite_runs = []
    for bench_name, _ in _resolve_bench_targets(args.bench, args.bench_root):
        payloads = _build_payloads_from_hf(bench_name=bench_name, limit=args.limit)
        manifest_path = _write_bench_payload_manifest(
            bench_name=bench_name,
            payloads=payloads,
            bench_root=args.bench_root,
        )
        bench_output_dir = args.output_dir / bench_name
        run_info = _run_single_manifest(
            manifest=manifest_path,
            output_dir=bench_output_dir,
            modes=args.modes,
            config_path=args.config_path,
            max_workers=args.max_workers,
        )
        run_info["bench"] = bench_name
        suite_runs.append(run_info)

    suite_summary_path = args.output_dir / "suite_summary.json"
    suite_summary_path.write_text(
        json.dumps(
            {
                "bench": args.bench,
                "bench_root": str(args.bench_root),
                "runs": suite_runs,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
