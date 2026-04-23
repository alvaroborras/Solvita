"""Parse and normalize benchmark results for resume / dedup / repeat-aware reporting."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Set, Tuple

DEFAULT_RESUME_STATUSES: frozenset[str] = frozenset({"success", "max_iterations", "max_iteration"})


def normalize_result_status(status: Any) -> str:
    s = str(status or "").strip()
    if s == "max_iteration":
        return "max_iterations"
    return s


def normalize_repeat_index(value: Any) -> int:
    try:
        return max(1, int(value or 1))
    except (TypeError, ValueError):
        return 1


def iter_parseable_result_rows(path: Path) -> Iterator[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            yield json.loads(stripped)
        except json.JSONDecodeError:
            continue


def build_result_key(row: Dict[str, Any], *, repeat_aware: bool) -> Tuple[Any, ...] | None:
    problem_id = str(row.get("problem_id", "") or "").strip()
    mode = str(row.get("mode", "") or "").strip()
    if not problem_id or not mode:
        return None
    if repeat_aware:
        return (problem_id, mode, normalize_repeat_index(row.get("repeat_index", 1)))
    return (problem_id, mode)


def index_resumable_rows(
    rows: Iterable[Dict[str, Any]],
    *,
    modes: Tuple[str, ...],
    statuses: Optional[Set[str]] = None,
    repeat_aware: bool = False,
) -> Dict[Tuple[Any, ...], Dict[str, Any]]:
    allowed: Set[str] = set(statuses) if statuses is not None else set(DEFAULT_RESUME_STATUSES)
    mode_set = set(modes)
    out: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    for row in rows:
        mode = str(row.get("mode", "") or "").strip()
        if mode not in mode_set:
            continue
        st = normalize_result_status(row.get("status"))
        if st == "error" or st not in allowed:
            continue
        key = build_result_key(row, repeat_aware=repeat_aware)
        if key is None:
            continue
        normalized = dict(row)
        normalized["status"] = st
        normalized["repeat_index"] = normalize_repeat_index(normalized.get("repeat_index", 1))
        out[key] = normalized
    return out


def problem_fully_resumed(
    problem_id: str,
    modes: Tuple[str, ...],
    resumable: Dict[Tuple[Any, ...], Dict[str, Any]],
    *,
    repeat_index: int = 1,
    repeat_aware: bool = False,
) -> bool:
    pid = str(problem_id or "").strip()
    if not pid:
        return False
    if repeat_aware:
        return all((pid, m, normalize_repeat_index(repeat_index)) in resumable for m in modes)
    return all((pid, m) in resumable for m in modes)


def load_resume_index(
    path: Path,
    *,
    modes: Tuple[str, ...],
    statuses: Optional[Set[str]] = None,
    repeat_aware: bool = False,
) -> Dict[Tuple[Any, ...], Dict[str, Any]]:
    return index_resumable_rows(
        iter_parseable_result_rows(path),
        modes=modes,
        statuses=statuses,
        repeat_aware=repeat_aware,
    )


def normalize_result_rows(rows: Iterable[Dict[str, Any]], *, repeat_aware: bool) -> List[Dict[str, Any]]:
    deduped: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    for row in rows:
        key = build_result_key(row, repeat_aware=repeat_aware)
        if key is None:
            continue
        normalized = dict(row)
        normalized["repeat_index"] = normalize_repeat_index(normalized.get("repeat_index", 1))
        normalized["status"] = normalize_result_status(normalized.get("status"))
        deduped[key] = normalized
    return [deduped[key] for key in sorted(deduped.keys())]


def write_normalized_results_jsonl(dst: Path, rows: Iterable[Dict[str, Any]], *, repeat_aware: bool) -> int:
    normalized_rows = normalize_result_rows(rows, repeat_aware=repeat_aware)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("w", encoding="utf-8") as out_fh:
        for row in normalized_rows:
            out_fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(normalized_rows)


def filter_resumable_rows(
    rows: Iterable[Dict[str, Any]],
    *,
    modes: Tuple[str, ...],
    statuses: Optional[Set[str]] = None,
    repeat_aware: bool = False,
) -> List[Dict[str, Any]]:
    indexed = index_resumable_rows(rows, modes=modes, statuses=statuses, repeat_aware=repeat_aware)
    return [indexed[key] for key in sorted(indexed.keys())]


def write_filtered_results_jsonl(
    src: Path,
    dst: Path,
    *,
    modes: Tuple[str, ...],
    statuses: Optional[Set[str]] = None,
    repeat_aware: bool = False,
) -> tuple[int, int]:
    allowed_rows = filter_resumable_rows(
        iter_parseable_result_rows(src),
        modes=modes,
        statuses=statuses,
        repeat_aware=repeat_aware,
    )
    dst.parent.mkdir(parents=True, exist_ok=True)
    skipped = 0
    text = src.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            json.loads(stripped)
        except json.JSONDecodeError:
            skipped += 1
    written = write_normalized_results_jsonl(dst, allowed_rows, repeat_aware=repeat_aware)
    return written, skipped


def resolve_resume_path_for_bench(resume_path: Optional[Path], bench_name: str) -> Optional[Path]:
    if resume_path is None:
        return None
    try:
        parent = resume_path.parent.name
    except Exception:
        return resume_path
    if parent in {"code-contest", "apps", "aethercode"}:
        return resume_path if parent == bench_name else None
    return resume_path
