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


def summarize_results(rows: Iterable[Any]) -> Dict[str, Any]:
    row_dicts = [_to_row_dict(row) for row in rows]
    by_mode: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    by_problem: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)

    for row in row_dicts:
        by_mode[row["mode"]].append(row)
        by_problem[row["problem_id"]][row["mode"]] = row

    mode_summary = {}
    for mode, items in by_mode.items():
        total = len(items)
        mode_summary[mode] = {
            "count": total,
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
        }

    wins_pipeline = 0
    wins_gpt52 = 0
    ties = 0
    for _, pair in by_problem.items():
        pipeline = pair.get("solvita_pipeline")
        single = pair.get("single_pass") or pair.get("gpt52_single_pass")
        if not pipeline or not single:
            continue
        p_rate = float(pipeline.get("pass_rate", 0.0))
        s_rate = float(single.get("pass_rate", 0.0))
        if p_rate > s_rate:
            wins_pipeline += 1
        elif s_rate > p_rate:
            wins_gpt52 += 1
        else:
            ties += 1

    return {
        "modes": mode_summary,
        "head_to_head": {
            "wins_pipeline": wins_pipeline,
            "wins_single_pass": wins_gpt52,
            "ties": ties,
        },
        "total_rows": len(row_dicts),
        "total_problems": len(by_problem),
    }


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
                f"- count: {stats['count']}",
                f"- compile_success_rate: {stats['compile_success_rate']:.2%}",
                f"- avg_pass_rate: {stats['avg_pass_rate']:.2%}",
                f"- avg_elapsed_total_s: {stats['avg_elapsed_total_s']:.2f}",
                f"- avg_llm_infer_s: {stats['avg_llm_infer_s']:.2f}",
                f"- avg_prompt_tokens: {stats['avg_prompt_tokens']:.2f}",
                f"- avg_completion_tokens: {stats['avg_completion_tokens']:.2f}",
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


def write_summary_outputs(output_dir: Path, rows: Iterable[Any]) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    row_dicts = [_to_row_dict(row) for row in rows]
    summary = summarize_results(row_dicts)

    summary_path = output_dir / "summary.json"
    report_path = output_dir / "report.md"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    report_path.write_text(render_markdown_report(summary), encoding="utf-8")
    return summary
