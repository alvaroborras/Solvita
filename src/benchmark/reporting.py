"""Benchmark aggregation and reporting helpers."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, is_dataclass
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List


def _to_row_dict(row: Any) -> Dict[str, Any]:
    if is_dataclass(row):
        data = asdict(row)
        if "pass_rate" not in data and hasattr(row, "pass_rate"):
            data["pass_rate"] = row.pass_rate
        return data
    return dict(row)


def summarize_results(rows: Iterable[Any], repeats: int = 1) -> Dict[str, Any]:
    row_dicts = [_to_row_dict(row) for row in rows]
    by_mode: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    by_problem_mode: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))

    for row in row_dicts:
        by_mode[row["mode"]].append(row)
        by_problem_mode[row["problem_id"]][row["mode"]].append(row)

    mode_summary = {}
    for mode, items in by_mode.items():
        total = len(items)
        problem_count = len({str(item.get("problem_id", "")) for item in items if item.get("problem_id")})
        verifier_items = [item for item in items if item.get("verifier_decision") is not None]
        false_accept_items = [item for item in items if item.get("false_accept") is not None]
        mode_summary[mode] = {
            "row_count": total,
            "problem_count": problem_count,
            "compile_success_rate": (
                sum(1 for item in items if item["compile_success"]) / total if total else 0.0
            ),
            "avg_pass_rate": (
                sum(float(item.get("pass_rate", 0.0)) for item in items) / total if total else 0.0
            ),
            "avg_elapsed_total_s": (
                sum(float(item.get("elapsed_total_s", 0.0)) for item in items) / total if total else 0.0
            ),
            "avg_llm_infer_s": (
                sum(float(item.get("llm_infer_s", 0.0)) for item in items) / total if total else 0.0
            ),
            "avg_prompt_tokens": (
                sum(float(item.get("prompt_tokens", 0.0) or 0.0) for item in items) / total if total else 0.0
            ),
            "avg_completion_tokens": (
                sum(float(item.get("completion_tokens", 0.0) or 0.0) for item in items) / total if total else 0.0
            ),
            "false_accept_rate": (
                sum(1 for item in false_accept_items if item.get("false_accept")) / len(false_accept_items)
                if false_accept_items else 0.0
            ),
            "verifier_accept_rate": (
                sum(1 for item in verifier_items if item.get("verifier_decision") == "accept") / len(verifier_items)
                if verifier_items else 0.0
            ),
            "verifier_repair_rate": (
                sum(1 for item in verifier_items if item.get("verifier_decision") == "repair") / len(verifier_items)
                if verifier_items else 0.0
            ),
            "verifier_escalation_rate": (
                sum(1 for item in verifier_items if item.get("verifier_decision") == "escalate_testgen") / len(verifier_items)
                if verifier_items else 0.0
            ),
            "full_testgen_completion_rate": (
                sum(1 for item in items if item.get("full_testgen_completed")) / total if total else 0.0
            ),
        }

    wins_pipeline = 0
    wins_gpt52 = 0
    ties = 0
    for _, pair in by_problem_mode.items():
        pipeline_rows = sorted(pair.get("solvita_pipeline", []), key=lambda row: int(row.get("repeat_index", 1) or 1))
        single_rows = sorted(pair.get("single_pass", []) or pair.get("gpt52_single_pass", []), key=lambda row: int(row.get("repeat_index", 1) or 1))
        if not pipeline_rows or not single_rows:
            continue
        p_rate = float(pipeline_rows[0].get("pass_rate", 0.0))
        s_rate = float(single_rows[0].get("pass_rate", 0.0))
        if p_rate > s_rate:
            wins_pipeline += 1
        elif s_rate > p_rate:
            wins_gpt52 += 1
        else:
            ties += 1

    return {
        "modes": mode_summary,
        "pass_at_k": _summarize_pass_at_k(row_dicts, repeats=repeats),
        "head_to_head": {
            "wins_pipeline": wins_pipeline,
            "wins_single_pass": wins_gpt52,
            "ties": ties,
        },
        "total_rows": len(row_dicts),
        "total_problems": len(by_problem_mode),
    }


def _summarize_pass_at_k(row_dicts: List[Dict[str, Any]], repeats: int = 1) -> Dict[str, Dict[str, Any]]:
    if repeats <= 1:
        return {}

    by_mode_problem: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for row in row_dicts:
        problem_id = row.get("problem_id")
        mode = row.get("mode")
        if not problem_id or not mode:
            continue
        by_mode_problem[str(mode)][str(problem_id)].append(row)

    summary: Dict[str, Dict[str, Any]] = {}
    for mode, problems in by_mode_problem.items():
        total = len(problems)
        if total == 0:
            continue

        full_pass_at_1 = 0
        full_pass_at_k = 0
        avg_pass_rate_at_1 = 0.0
        avg_best_of_k_pass_rate = 0.0

        for rows in problems.values():
            ordered = sorted(rows, key=lambda row: int(row.get("repeat_index", 1) or 1))
            first = ordered[0]
            first_rate = float(first.get("pass_rate", 0.0) or 0.0)
            best_rate = max(float(row.get("pass_rate", 0.0) or 0.0) for row in ordered)

            if first_rate >= 1.0:
                full_pass_at_1 += 1
            if any(float(row.get("pass_rate", 0.0) or 0.0) >= 1.0 for row in ordered):
                full_pass_at_k += 1

            avg_pass_rate_at_1 += first_rate
            avg_best_of_k_pass_rate += best_rate

        summary[mode] = {
            "k": repeats,
            "problem_count": total,
            "full_pass_at_1": full_pass_at_1,
            "full_pass_at_k": full_pass_at_k,
            "full_pass_at_1_rate": full_pass_at_1 / total,
            "full_pass_at_k_rate": full_pass_at_k / total,
            "avg_pass_rate_at_1": avg_pass_rate_at_1 / total,
            "avg_best_of_k_pass_rate": avg_best_of_k_pass_rate / total,
        }

    return summary


def render_markdown_report(summary: Dict[str, Any]) -> str:
    lines = [
        "# Benchmark Report",
        "",
        "## Mode Summary",
        "",
    ]

    for mode, stats in summary.get("modes", {}).items():
        lines.extend(
            [
                f"### {mode}",
                f"- row_count: {stats['row_count']}",
                f"- problem_count: {stats['problem_count']}",
                f"- compile_success_rate: {stats['compile_success_rate']:.2%}",
                f"- avg_pass_rate: {stats['avg_pass_rate']:.2%}",
                f"- avg_elapsed_total_s: {stats['avg_elapsed_total_s']:.2f}",
                f"- avg_llm_infer_s: {stats['avg_llm_infer_s']:.2f}",
                f"- avg_prompt_tokens: {stats['avg_prompt_tokens']:.2f}",
                f"- avg_completion_tokens: {stats['avg_completion_tokens']:.2f}",
                f"- false_accept_rate: {stats.get('false_accept_rate', 0.0):.2%}",
                f"- verifier_accept_rate: {stats.get('verifier_accept_rate', 0.0):.2%}",
                f"- verifier_repair_rate: {stats.get('verifier_repair_rate', 0.0):.2%}",
                f"- verifier_escalation_rate: {stats.get('verifier_escalation_rate', 0.0):.2%}",
                f"- full_testgen_completion_rate: {stats.get('full_testgen_completion_rate', 0.0):.2%}",
                "",
            ]
        )

    pass_at_k = summary.get("pass_at_k", {})
    if pass_at_k:
        lines.extend([
            "## Pass@K",
            "",
        ])
        for mode, stats in pass_at_k.items():
            lines.extend(
                [
                    f"### {mode}",
                    f"- k: {stats['k']}",
                    f"- problem_count: {stats['problem_count']}",
                    f"- full_pass_at_1: {stats['full_pass_at_1']}",
                    f"- full_pass_at_k: {stats['full_pass_at_k']}",
                    f"- full_pass_at_1_rate: {stats['full_pass_at_1_rate']:.2%}",
                    f"- full_pass_at_k_rate: {stats['full_pass_at_k_rate']:.2%}",
                    f"- avg_pass_rate_at_1: {stats['avg_pass_rate_at_1']:.2%}",
                    f"- avg_best_of_k_pass_rate: {stats['avg_best_of_k_pass_rate']:.2%}",
                    "",
                ]
            )

    h2h = summary.get("head_to_head", {})
    lines.extend(
        [
            "## Head-to-Head",
            "",
            f"- wins_pipeline: {h2h.get('wins_pipeline', 0)}",
            f"- wins_single_pass: {h2h.get('wins_single_pass', 0)}",
            f"- ties: {h2h.get('ties', 0)}",
            "",
        ]
    )
    return "\n".join(lines)


def write_summary_outputs(output_dir: Path, rows: Iterable[Any], repeats: int = 1) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    row_dicts = [_to_row_dict(row) for row in rows]
    summary = summarize_results(row_dicts, repeats=repeats)

    summary_path = output_dir / "summary.json"
    report_path = output_dir / "report.md"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    report_path.write_text(render_markdown_report(summary), encoding="utf-8")
    return summary
