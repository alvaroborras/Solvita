from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LEGACY_DEFAULTS = {
    "fallback_family_id": "",
    "artifact_kind": "",
    "decision": "",
    "certified_count": 0,
    "certified_target_count": 0,
    "cert_ratio": 0.0,
    "reward": 0.0,
    "reward_reason": "",
    "failure_stage": "",
    "failure_subtype": "",
    "checker_fallback_used": False,
    "solver_attempt_count": 0,
    "selected_template_name": "",
    "compact_retry_count": 0,
    "prompt_char_stats": {},
    "cost": {},
}

REQUIRED_AUDIT_FIELDS = tuple(LEGACY_DEFAULTS.keys())

EMPTY_CONTEXT = {
    "problem_source_path": "",
    "problem_tags_joined": "",
    "canonical_tags_joined": "",
    "problem_type_joined": "",
    "key_elements_joined": "",
    "objective_text": "",
    "graph_type": "",
    "is_multi_solution": False,
    "data_structures_joined": "",
    "constraints_json": "",
    "description_chars": 0,
    "public_tests_count": 0,
    "has_problem_context": 0,
}

CSV_FIELD_ORDER = [
    "problem_id",
    "source_path",
    "problem_source_path",
    "record_schema_version",
    "has_audit_fields",
    "has_problem_context",
    "route",
    "trainability_class",
    "candidate_family_pool",
    "candidate_family_pool_size",
    "candidate_family_pool_joined",
    "selected_family_id",
    "fallback_family_id",
    "selected_is_fallback",
    "decision",
    "artifact_kind",
    "compile_success",
    "public_self_check_pass",
    "probe_pack_pass",
    "certified_count",
    "certified_target_count",
    "cert_ratio",
    "reward",
    "reward_reason",
    "failure_stage",
    "failure_subtype",
    "checker_fallback_used",
    "solver_attempt_count",
    "selected_template_name",
    "compact_retry_count",
    "cost_llm_calls",
    "prompt_char_stats",
    "prompt_chars_generator",
    "prompt_chars_validator",
    "prompt_chars_checker",
    "prompt_chars_solver",
    "problem_tags_joined",
    "canonical_tags_joined",
    "problem_type_joined",
    "key_elements_joined",
    "objective_text",
    "graph_type",
    "is_multi_solution",
    "data_structures_joined",
    "constraints_json",
    "description_chars",
    "public_tests_count",
    "is_trusted_label",
    "sample_weight",
]


def _coerce_int(value: Any) -> int:
    if value in ("", None):
        return 0
    return int(value)


def _coerce_float(value: Any) -> float:
    if value in ("", None):
        return 0.0
    return float(value)


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _coerce_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)]


def _join_values(value: Any) -> str:
    return "|".join(_coerce_list(value))


def _json_string(value: Any) -> str:
    if value in ("", None, {}, []):
        return ""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _build_problem_context(problem_row: dict[str, Any] | None) -> dict[str, Any]:
    if not problem_row:
        return dict(EMPTY_CONTEXT)

    canonical = problem_row.get("canonical")
    canonical = canonical if isinstance(canonical, dict) else {}

    raw_tags = problem_row.get("tags") or problem_row.get("problem_tags") or []
    canonical_tags = canonical.get("tags") or raw_tags
    problem_type = canonical.get("problem_type") or problem_row.get("problem_type") or []
    key_elements = canonical.get("key_elements") or problem_row.get("key_elements") or []
    objective_text = canonical.get("objective") or problem_row.get("objective") or problem_row.get("objective_text") or ""
    graph_type = canonical.get("graph_type") or problem_row.get("graph_type") or ""
    is_multi_solution = (
        canonical.get("is_multi_solution")
        if "is_multi_solution" in canonical
        else problem_row.get("is_multi_solution", False)
    )
    data_structures = canonical.get("data_structures") or problem_row.get("data_structures") or []
    constraints = canonical.get("constraints") or problem_row.get("constraints") or ""
    description = problem_row.get("description") or problem_row.get("problem") or ""
    public_tests = problem_row.get("public_tests") or problem_row.get("test_case") or []

    return {
        "problem_source_path": str(problem_row.get("__problem_source_path", "")),
        "problem_tags_joined": _join_values(raw_tags or canonical_tags),
        "canonical_tags_joined": _join_values(canonical_tags),
        "problem_type_joined": _join_values(problem_type),
        "key_elements_joined": _join_values(key_elements),
        "objective_text": str(objective_text or ""),
        "graph_type": str(graph_type or ""),
        "is_multi_solution": _coerce_bool(is_multi_solution),
        "data_structures_joined": _join_values(data_structures),
        "constraints_json": _json_string(constraints),
        "description_chars": len(str(description or "")),
        "public_tests_count": len(public_tests) if isinstance(public_tests, list) else 0,
        "has_problem_context": 1,
    }


def normalize_candidate_record(record: dict, source_path: Path) -> dict:
    candidate_family_pool = _coerce_list(record.get("candidate_family_pool"))
    prompt_char_stats = record.get("prompt_char_stats")
    prompt_char_stats = prompt_char_stats if isinstance(prompt_char_stats, dict) else {}
    cost = record.get("cost")
    cost = cost if isinstance(cost, dict) else {}
    has_audit_fields = int(all(field in record for field in REQUIRED_AUDIT_FIELDS))

    normalized = {
        "problem_id": str(record.get("problem_id", "")),
        "route": str(record.get("route") or record.get("trainability_class") or ""),
        "trainability_class": str(record.get("trainability_class") or record.get("route") or ""),
        "candidate_family_pool": candidate_family_pool,
        "selected_family_id": str(record.get("selected_family_id", "")),
        "fallback_family_id": str(record.get("fallback_family_id", LEGACY_DEFAULTS["fallback_family_id"])),
        "compile_success": _coerce_bool(record.get("compile_success", False)),
        "public_self_check_pass": _coerce_bool(record.get("public_self_check_pass", False)),
        "probe_pack_pass": _coerce_bool(record.get("probe_pack_pass", False)),
        "artifact_kind": str(record.get("artifact_kind", LEGACY_DEFAULTS["artifact_kind"])),
        "decision": str(record.get("decision", LEGACY_DEFAULTS["decision"])),
        "certified_count": _coerce_int(record.get("certified_count", LEGACY_DEFAULTS["certified_count"])),
        "certified_target_count": _coerce_int(
            record.get("certified_target_count", LEGACY_DEFAULTS["certified_target_count"])
        ),
        "cert_ratio": _coerce_float(record.get("cert_ratio", LEGACY_DEFAULTS["cert_ratio"])),
        "reward": _coerce_float(record.get("reward", LEGACY_DEFAULTS["reward"])),
        "reward_reason": str(record.get("reward_reason", LEGACY_DEFAULTS["reward_reason"])),
        "failure_stage": str(record.get("failure_stage", LEGACY_DEFAULTS["failure_stage"])),
        "failure_subtype": str(record.get("failure_subtype", LEGACY_DEFAULTS["failure_subtype"])),
        "checker_fallback_used": _coerce_bool(
            record.get("checker_fallback_used", LEGACY_DEFAULTS["checker_fallback_used"])
        ),
        "solver_attempt_count": _coerce_int(
            record.get("solver_attempt_count", LEGACY_DEFAULTS["solver_attempt_count"])
        ),
        "selected_template_name": str(
            record.get("selected_template_name", LEGACY_DEFAULTS["selected_template_name"])
        ),
        "compact_retry_count": _coerce_int(record.get("compact_retry_count", LEGACY_DEFAULTS["compact_retry_count"])),
        "prompt_char_stats": dict(prompt_char_stats),
        "cost": dict(cost),
        "source_path": str(source_path),
        "record_schema_version": "audit_v1" if has_audit_fields else "legacy_v0",
        "has_audit_fields": has_audit_fields,
        "candidate_family_pool_size": len(candidate_family_pool),
        "candidate_family_pool_joined": _join_values(candidate_family_pool),
        "cost_llm_calls": _coerce_int(cost.get("llm_calls", 0)),
    }
    normalized["selected_is_fallback"] = int(
        normalized["selected_family_id"] == normalized["fallback_family_id"]
    )
    normalized.update(EMPTY_CONTEXT)
    return normalized


def load_problem_source(
    problem_source_path: Path,
    required_problem_ids: set[str] | None = None,
) -> dict[str, dict]:
    if problem_source_path.is_dir():
        raise ValueError(f"problem-source must be a single JSONL file, not a directory: {problem_source_path}")
    if problem_source_path.suffix != ".jsonl":
        raise ValueError(f"problem-source must be a single JSONL file: {problem_source_path}")
    if not problem_source_path.exists():
        raise FileNotFoundError(problem_source_path)

    required_ids = None
    if required_problem_ids is not None:
        required_ids = {str(problem_id) for problem_id in required_problem_ids if problem_id not in (None, "")}

    index: dict[str, dict] = {}
    with problem_source_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            problem_id = row.get("id") or row.get("problem_id")
            if not problem_id:
                continue
            problem_id = str(problem_id)
            if required_ids is not None and problem_id not in required_ids:
                continue
            indexed_row = dict(row)
            indexed_row["__problem_source_path"] = str(problem_source_path)
            index[problem_id] = indexed_row
    return index


def join_problem_context(record: dict, problem_index: dict[str, dict]) -> dict:
    joined = dict(record)
    joined.update(_build_problem_context(problem_index.get(record.get("problem_id", ""))))
    return joined


def compute_trusted_label(record: dict) -> tuple[int, float]:
    is_trusted = int(
        record.get("has_problem_context", 0) == 1
        and record.get("decision") == "accept"
        and record.get("artifact_kind") == "expected_output"
        and record.get("compile_success") is True
        and record.get("public_self_check_pass") is True
        and record.get("probe_pack_pass") is True
        and _coerce_int(record.get("certified_target_count", 0)) > 0
        and _coerce_int(record.get("certified_count", 0)) == _coerce_int(record.get("certified_target_count", 0))
        and _coerce_float(record.get("cert_ratio", 0.0)) >= 1.0
        and record.get("reward_reason") == "fully_certified"
    )
    return is_trusted, 1.0 if is_trusted else 0.0


def flatten_record_for_csv(record: dict) -> dict:
    prompt_char_stats = record.get("prompt_char_stats")
    prompt_char_stats = prompt_char_stats if isinstance(prompt_char_stats, dict) else {}
    flattened = {
        "problem_id": record.get("problem_id", ""),
        "source_path": record.get("source_path", ""),
        "problem_source_path": record.get("problem_source_path", ""),
        "record_schema_version": record.get("record_schema_version", ""),
        "has_audit_fields": _coerce_int(record.get("has_audit_fields", 0)),
        "has_problem_context": _coerce_int(record.get("has_problem_context", 0)),
        "route": record.get("route", ""),
        "trainability_class": record.get("trainability_class", ""),
        "candidate_family_pool": json.dumps(record.get("candidate_family_pool", []), ensure_ascii=False),
        "candidate_family_pool_size": _coerce_int(record.get("candidate_family_pool_size", 0)),
        "candidate_family_pool_joined": record.get("candidate_family_pool_joined", ""),
        "selected_family_id": record.get("selected_family_id", ""),
        "fallback_family_id": record.get("fallback_family_id", ""),
        "selected_is_fallback": _coerce_int(record.get("selected_is_fallback", 0)),
        "decision": record.get("decision", ""),
        "artifact_kind": record.get("artifact_kind", ""),
        "compile_success": _coerce_int(record.get("compile_success", False)),
        "public_self_check_pass": _coerce_int(record.get("public_self_check_pass", False)),
        "probe_pack_pass": _coerce_int(record.get("probe_pack_pass", False)),
        "certified_count": _coerce_int(record.get("certified_count", 0)),
        "certified_target_count": _coerce_int(record.get("certified_target_count", 0)),
        "cert_ratio": _coerce_float(record.get("cert_ratio", 0.0)),
        "reward": _coerce_float(record.get("reward", 0.0)),
        "reward_reason": record.get("reward_reason", ""),
        "failure_stage": record.get("failure_stage", ""),
        "failure_subtype": record.get("failure_subtype", ""),
        "checker_fallback_used": _coerce_int(record.get("checker_fallback_used", False)),
        "solver_attempt_count": _coerce_int(record.get("solver_attempt_count", 0)),
        "selected_template_name": record.get("selected_template_name", ""),
        "compact_retry_count": _coerce_int(record.get("compact_retry_count", 0)),
        "cost_llm_calls": _coerce_int(record.get("cost_llm_calls", 0)),
        "prompt_char_stats": json.dumps(prompt_char_stats, ensure_ascii=False, sort_keys=True),
        "prompt_chars_generator": _coerce_int(prompt_char_stats.get("generator", 0)),
        "prompt_chars_validator": _coerce_int(prompt_char_stats.get("validator", 0)),
        "prompt_chars_checker": _coerce_int(prompt_char_stats.get("checker", 0)),
        "prompt_chars_solver": _coerce_int(prompt_char_stats.get("solver", 0)),
        "problem_tags_joined": record.get("problem_tags_joined", ""),
        "canonical_tags_joined": record.get("canonical_tags_joined", ""),
        "problem_type_joined": record.get("problem_type_joined", ""),
        "key_elements_joined": record.get("key_elements_joined", ""),
        "objective_text": record.get("objective_text", ""),
        "graph_type": record.get("graph_type", ""),
        "is_multi_solution": _coerce_int(record.get("is_multi_solution", False)),
        "data_structures_joined": record.get("data_structures_joined", ""),
        "constraints_json": record.get("constraints_json", ""),
        "description_chars": _coerce_int(record.get("description_chars", 0)),
        "public_tests_count": _coerce_int(record.get("public_tests_count", 0)),
        "is_trusted_label": _coerce_int(record.get("is_trusted_label", 0)),
        "sample_weight": _coerce_float(record.get("sample_weight", 0.0)),
    }

    for key, value in prompt_char_stats.items():
        flattened[f"prompt_chars_{key}"] = _coerce_int(value)
    return flattened


def _load_input_records(input_paths: list[Path]) -> tuple[int, list[dict[str, Any]]]:
    total_input_samples = 0
    normalized_records: list[dict[str, Any]] = []
    for input_path in input_paths:
        if input_path.is_dir():
            raise ValueError(f"input path must be a JSONL file, not a directory: {input_path}")
        with input_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                total_input_samples += 1
                normalized_records.append(normalize_candidate_record(json.loads(line), input_path))
    return total_input_samples, normalized_records


def _is_audit_eligible(record: dict) -> bool:
    candidate_family_pool = record.get("candidate_family_pool", [])
    return (
        record.get("route") == "exact_single_answer"
        and len(candidate_family_pool) >= 2
        and record.get("selected_family_id") in candidate_family_pool
    )


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flattened_records = [flatten_record_for_csv(record) for record in records]
    fieldnames = list(CSV_FIELD_ORDER)
    extra_fields: list[str] = []
    for row in flattened_records:
        for key in row:
            if key not in fieldnames and key not in extra_fields:
                extra_fields.append(key)
    fieldnames.extend(sorted(extra_fields))

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(flattened_records)


def _build_summary(
    *,
    total_input_samples: int,
    normalized_records: list[dict[str, Any]],
    audit_records: list[dict[str, Any]],
    trusted_records: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "total_input_samples": total_input_samples,
        "normalized_samples": len(normalized_records),
        "audit_all_samples": len(audit_records),
        "trusted_train_subset_samples": len(trusted_records),
        "filtered_samples": len(normalized_records) - len(audit_records),
        "record_schema_version": dict(Counter(record["record_schema_version"] for record in normalized_records)),
        "has_problem_context": dict(Counter(record["has_problem_context"] for record in audit_records)),
        "selected_family_id": dict(Counter(record["selected_family_id"] for record in audit_records)),
        "candidate_family_pool_size": dict(Counter(record["candidate_family_pool_size"] for record in audit_records)),
        "reward_reason": dict(Counter(record["reward_reason"] for record in audit_records)),
        "is_trusted_label": dict(Counter(record["is_trusted_label"] for record in audit_records)),
    }


def _print_summary(summary: dict[str, Any]) -> None:
    for key in [
        "total_input_samples",
        "normalized_samples",
        "audit_all_samples",
        "trusted_train_subset_samples",
        "filtered_samples",
        "record_schema_version",
        "has_problem_context",
        "selected_family_id",
        "candidate_family_pool_size",
        "reward_reason",
        "is_trusted_label",
    ]:
        value = summary[key]
        if isinstance(value, dict):
            print(f"{key}: {json.dumps(value, ensure_ascii=False, sort_keys=True)}")
        else:
            print(f"{key}: {value}")


def export_selector_dataset(
    input_paths: list[Path],
    problem_source_path: Path | None,
    output_dir: Path,
    prefix: str,
) -> dict:
    total_input_samples, normalized_records = _load_input_records(input_paths)
    audit_records = [dict(record) for record in normalized_records if _is_audit_eligible(record)]

    if problem_source_path is not None:
        required_problem_ids = {
            str(record["problem_id"])
            for record in audit_records
            if record.get("problem_id") not in (None, "")
        }
        problem_index = (
            load_problem_source(problem_source_path, required_problem_ids=required_problem_ids)
            if required_problem_ids
            else {}
        )
        audit_records = [join_problem_context(record, problem_index) for record in audit_records]

    for record in audit_records:
        is_trusted_label, sample_weight = compute_trusted_label(record)
        record["is_trusted_label"] = is_trusted_label
        record["sample_weight"] = sample_weight

    trusted_records = [dict(record) for record in audit_records if record["is_trusted_label"] == 1]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir.mkdir(parents=True, exist_ok=True)

    audit_jsonl = output_dir / f"{prefix}_audit_all_{timestamp}.jsonl"
    audit_csv = output_dir / f"{prefix}_audit_all_{timestamp}.csv"
    _write_jsonl(audit_jsonl, audit_records)
    _write_csv(audit_csv, audit_records)

    trusted_jsonl: Path | None = None
    trusted_csv: Path | None = None
    if problem_source_path is not None:
        trusted_jsonl = output_dir / f"{prefix}_trusted_train_subset_{timestamp}.jsonl"
        trusted_csv = output_dir / f"{prefix}_trusted_train_subset_{timestamp}.csv"
        _write_jsonl(trusted_jsonl, trusted_records)
        _write_csv(trusted_csv, trusted_records)

    summary = _build_summary(
        total_input_samples=total_input_samples,
        normalized_records=normalized_records,
        audit_records=audit_records,
        trusted_records=trusted_records,
    )
    _print_summary(summary)

    return {
        "audit_jsonl": audit_jsonl,
        "audit_csv": audit_csv,
        "trusted_jsonl": trusted_jsonl,
        "trusted_csv": trusted_csv,
        "summary": summary,
    }
