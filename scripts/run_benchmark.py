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

from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.benchmark.dataset import load_benchmark_manifest
from src.benchmark.modes.single_pass import run_single_pass_case
from src.benchmark.modes.pipeline import run_pipeline_benchmark_case
from src.benchmark.reporting import write_summary_outputs
from src.benchmark.results_resume import (
    iter_parseable_result_rows,
    load_resume_index,
    normalize_result_rows,
    problem_fully_resumed,
    write_normalized_results_jsonl,
)


MODE_RUNNERS = {
    "solvita_pipeline": run_pipeline_benchmark_case,
    "single_pass": run_single_pass_case,
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
        default=["solvita_pipeline", "single_pass"],
        choices=sorted(MODE_RUNNERS.keys()),
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Number of independent repeats per problem.",
    )
    parser.add_argument(
        "--apps-difficulty",
        type=str,
        default=None,
        choices=["introductory", "interview", "competition"],
        help="Filter APPS dataset by difficulty level.",
    )
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
    parser.add_argument(
        "--solver-network",
        action="store_true",
        default=False,
        help="Enable solver_network for pipeline mode.",
    )
    parser.add_argument(
        "--trainable-memory",
        action="store_true",
        default=False,
        help="Enable trainable_memory for pipeline mode.",
    )
    parser.add_argument(
        "--tm-hacker",
        action="store_true",
        default=None,
        help="Enable hacker sub-network within trainable_memory (implies --trainable-memory).",
    )
    parser.add_argument(
        "--tm-oracle",
        action="store_true",
        default=None,
        help="Enable oracle sub-network within trainable_memory (implies --trainable-memory).",
    )
    parser.add_argument(
        "--no-tm-hacker",
        action="store_true",
        default=False,
        help="Disable hacker sub-network within trainable_memory.",
    )
    parser.add_argument(
        "--no-tm-oracle",
        action="store_true",
        default=False,
        help="Disable oracle sub-network within trainable_memory.",
    )
    parser.add_argument(
        "--disable-hacker",
        action="store_true",
        default=False,
        help="Disable the workflow hacker phase for pipeline mode.",
    )
    return parser.parse_args()


def load_problem_payload(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_problem_modes(
    item: Any,
    modes: List[str],
    config: Dict[str, Any],
    repeat_index: int = 1,
) -> List[Dict[str, Any]]:
    payload = load_problem_payload(item.problem_payload_path)
    rows: List[Dict[str, Any]] = []
    run_config = dict(config)
    run_config["benchmark_repeat_index"] = repeat_index

    for mode in modes:
        runner = MODE_RUNNERS[mode]
        try:
            result = runner(problem_payload=payload, config=run_config)
            row = {
                "problem_id": result.problem_id,
                "repeat_index": repeat_index,
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
                "verifier_decision": result.verifier_decision,
                "verifier_confidence": result.verifier_confidence,
                "false_accept": result.false_accept,
                "full_testgen_completed": result.full_testgen_completed,
            }
        except Exception as exc:
            row = {
                "problem_id": item.problem_id,
                "repeat_index": repeat_index,
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
                "verifier_decision": None,
                "verifier_confidence": None,
                "false_accept": None,
                "full_testgen_completed": None,
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
    repeat: int = 1,
    solver_network: bool = False,
    trainable_memory: bool = False,
    tm_hacker_enabled: bool | None = None,
    tm_oracle_enabled: bool | None = None,
    hacker_enabled: bool = True,
) -> Dict[str, Any]:
    items = load_benchmark_manifest(manifest)
    if limit is not None:
        items = items[:limit]
    output_dir.mkdir(parents=True, exist_ok=True)
    results_path = output_dir / "results.jsonl"

    tm_config: Dict[str, Any] = {"enabled": trainable_memory}
    if tm_hacker_enabled is not None:
        tm_config["hacker_enabled"] = tm_hacker_enabled
    if tm_oracle_enabled is not None:
        tm_config["oracle_enabled"] = tm_oracle_enabled

    config = {
        "config_path": config_path,
        "benchmark_output_dir": str(output_dir),
        "solver_network": {"enabled": solver_network},
        "workflow": {
            "hacker_enabled": hacker_enabled,
        },
        "trainable_memory": tm_config,
    }
    rows: List[Dict[str, Any]] = []
    worker_count = max(1, int(max_workers))
    total_repeats = max(1, int(repeat))
    repeat_aware = total_repeats > 1

    if results_path.exists():
        historical_rows = list(iter_parseable_result_rows(results_path))
        resumable_index = load_resume_index(
            results_path,
            modes=tuple(modes),
            repeat_aware=repeat_aware,
        )
    else:
        historical_rows = []
        resumable_index = {}

    jobs = []
    skipped_jobs = 0
    for repeat_index in range(1, total_repeats + 1):
        for item in items:
            if problem_fully_resumed(
                item.problem_id,
                tuple(modes),
                resumable_index,
                repeat_index=repeat_index,
                repeat_aware=repeat_aware,
            ):
                skipped_jobs += 1
            else:
                completed_modes = {
                    row["mode"]
                    for key, row in resumable_index.items()
                    if key[:1] == (item.problem_id,) and (not repeat_aware or key[2] == repeat_index)
                }
                pending_modes = [mode for mode in modes if mode not in completed_modes]
                jobs.append((item, repeat_index, pending_modes))

    if skipped_jobs:
        logger.info(
            "[Resume] Skipping {}/{} already-completed problem repeats",
            skipped_jobs,
            len(items) * total_repeats,
        )

    if not jobs:
        logger.info("[Resume] All problems already completed, nothing to do.")
        if results_path.exists():
            rows = normalize_result_rows(iter_parseable_result_rows(results_path), repeat_aware=repeat_aware)
        else:
            results_path.touch()
        write_normalized_results_jsonl(results_path, rows, repeat_aware=repeat_aware)
        write_summary_outputs(output_dir, rows, repeats=repeat)
        return {"results_path": str(results_path), "total": len(rows)}

    prefilled_rows = []
    if results_path.exists():
        prefilled_rows = list(iter_parseable_result_rows(results_path))
    rows = list(prefilled_rows)

    with results_path.open("a", encoding="utf-8") as fh:
        if worker_count == 1 or len(jobs) <= 1:
            for item, repeat_index, pending_modes in jobs:
                for row in _run_problem_modes(item, pending_modes, config, repeat_index=repeat_index):
                    rows.append(row)
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                    fh.flush()
        else:
            worker_count = min(worker_count, len(jobs), os.cpu_count() or worker_count)
            with ProcessPoolExecutor(max_workers=worker_count) as executor:
                future_to_problem = {
                    executor.submit(_run_problem_modes, item, pending_modes, config, repeat_index): (
                        item.problem_id,
                        repeat_index,
                        pending_modes,
                    )
                    for item, repeat_index, pending_modes in jobs
                }
                for future in as_completed(future_to_problem):
                    problem_id, repeat_index, pending_modes = future_to_problem[future]
                    try:
                        result_rows = future.result()
                    except Exception as exc:
                        logger.error(
                            "[Benchmark] Worker crashed for {} repeat {}: {}", problem_id, repeat_index, exc,
                        )
                        result_rows = [
                            {
                                "problem_id": problem_id,
                                "repeat_index": repeat_index,
                                "mode": m,
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
                                "error": f"Worker process crashed: {exc}",
                                "hack_result": None,
                                "hack_passed": None,
                                "generator_failure_kind": None,
                                "generator_failure_reason": None,
                                "workflow_log_path": None,
                            }
                            for m in pending_modes
                        ]
                    for row in result_rows:
                        rows.append(row)
                        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                        fh.flush()

    normalized_rows = normalize_result_rows(rows, repeat_aware=repeat_aware)
    write_normalized_results_jsonl(results_path, normalized_rows, repeat_aware=repeat_aware)
    summary = write_summary_outputs(output_dir, normalized_rows, repeats=repeat)
    return {
        "manifest": str(manifest),
        "output_dir": str(output_dir),
        "rows": len(normalized_rows),
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


def _build_raw_problem(
    bench: str,
    row: Dict[str, Any],
    public_tests: List[Dict[str, str]],
    problem_id: str,
) -> Dict[str, Any]:
    description = (
        row.get("description")
        or row.get("question")
        or row.get("problem")
        or row.get("statement")
        or ""
    )
    time_limit = row.get("time_limit") or row.get("time_limit_ms")
    space_limit = row.get("space_limit") or row.get("memory_limit") or row.get("memory_limit_mb")
    title = row.get("name") or row.get("title") or problem_id
    metadata = {
        "benchmark_source": bench,
        "dataset": BENCH_TO_HF_SOURCE[bench]["dataset"],
        "problem_id": problem_id,
        "name": str(title),
    }
    for key in ("question_id", "id", "task_id"):
        value = row.get(key)
        if value is not None:
            metadata[key] = str(value)
    return {
        "description": str(description),
        "time_limit": int(time_limit) if isinstance(time_limit, (int, float)) else 2000,
        "space_limit": int(space_limit) if isinstance(space_limit, (int, float)) else 256,
        "public_tests": public_tests,
        "_metadata": metadata,
    }


def _build_payloads_from_hf(bench_name: str, limit: int | None, apps_difficulty: str | None = None) -> List[Dict[str, Any]]:
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
        if bench_name == "aethercode":
            # aethercode has nested parquet fields (list<struct>) that crash
            # pandas/HF datasets conversion. Read with pyarrow directly.
            import glob as _glob
            import pyarrow.parquet as _pq
            from huggingface_hub import snapshot_download
            repo_id = source["dataset"]
            subset = source.get("name", "")
            cache_dir = snapshot_download(repo_id, repo_type="dataset")
            pattern = f"{cache_dir}/{subset}/*test*.parquet" if subset else f"{cache_dir}/*test*.parquet"
            pq_files = sorted(_glob.glob(pattern))
            if not pq_files:
                pattern = f"{cache_dir}/**/*test*.parquet"
                pq_files = sorted(_glob.glob(pattern, recursive=True))
            if not pq_files:
                raise SystemExit(f"No test parquet files found for aethercode in {cache_dir}")

            def _aethercode_rows():
                for pf in pq_files:
                    pf_obj = _pq.ParquetFile(pf)
                    for batch in pf_obj.iter_batches(batch_size=1):
                        yield {col: batch.column(col)[0].as_py() for col in batch.column_names}

            rows_iter = _aethercode_rows()
        else:
            try:
                from datasets import load_dataset
            except ImportError as exc:
                raise SystemExit("Missing dependency 'datasets'. Install it to use --bench mode.") from exc
            load_kwargs: Dict[str, Any] = {"split": source["split"]}
            if "name" in source:
                load_kwargs["name"] = source["name"]
            load_kwargs["streaming"] = True
            rows_iter = load_dataset(source["dataset"], **load_kwargs)

    payloads: List[Dict[str, Any]] = []
    for idx, row in enumerate(rows_iter):
        if not isinstance(row, dict):
            continue
        if bench_name == "apps" and apps_difficulty:
            if str(row.get("difficulty", "")).lower() != apps_difficulty.lower():
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
                "raw_problem": _build_raw_problem(bench_name, row, public_tests, problem_id),
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

    # Avoid race condition when multiple configs run in parallel —
    # if the manifest already exists with the right count, reuse it.
    if manifest_path.exists():
        existing = sum(1 for line in manifest_path.read_text(encoding="utf-8").splitlines() if line.strip())
        if existing == len(payloads):
            return manifest_path

    # Write to a temp file first, then atomically rename.
    import tempfile
    tmp_fd, tmp_path = tempfile.mkstemp(dir=str(cache_root), suffix=".jsonl")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
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
        os.replace(tmp_path, str(manifest_path))
    except BaseException:
        os.unlink(tmp_path)
        raise
    return manifest_path


def main() -> None:
    args = parse_args()
    if args.bench is None and args.manifest is None:
        raise SystemExit("Either --manifest or --bench must be provided.")

    # Resolve trainable_memory sub-network flags
    tm_enabled = args.trainable_memory
    tm_hacker: bool | None = None
    tm_oracle: bool | None = None

    if args.tm_hacker:
        tm_enabled = True
        tm_hacker = True
    if args.tm_oracle:
        tm_enabled = True
        tm_oracle = True
    if args.no_tm_hacker:
        tm_hacker = False
    if args.no_tm_oracle:
        tm_oracle = False

    common_kwargs = dict(
        solver_network=args.solver_network,
        trainable_memory=tm_enabled,
        tm_hacker_enabled=tm_hacker,
        tm_oracle_enabled=tm_oracle,
        hacker_enabled=not args.disable_hacker,
    )

    if args.bench is None:
        _run_single_manifest(
            manifest=args.manifest,
            output_dir=args.output_dir,
            modes=args.modes,
            config_path=args.config_path,
            max_workers=args.max_workers,
            limit=args.limit,
            repeat=args.repeat,
            **common_kwargs,
        )
        return

    args.output_dir.mkdir(parents=True, exist_ok=True)
    suite_runs = []
    for bench_name, _ in _resolve_bench_targets(args.bench, args.bench_root):
        payloads = _build_payloads_from_hf(bench_name=bench_name, limit=args.limit, apps_difficulty=args.apps_difficulty)
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
            repeat=args.repeat,
            **common_kwargs,
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
