from src.benchmark.reporting import render_markdown_report, summarize_results


def test_summarize_results_computes_head_to_head():
    rows = [
        {
            "problem_id": "p1",
            "mode": "solvita_pipeline",
            "pass_rate": 1.0,
            "compile_success": True,
            "elapsed_total_s": 2.0,
            "llm_infer_s": 1.0,
            "prompt_tokens": 100,
            "completion_tokens": 40,
        },
        {
            "problem_id": "p1",
            "mode": "single_pass",
            "pass_rate": 0.5,
            "compile_success": True,
            "elapsed_total_s": 1.0,
            "llm_infer_s": 0.8,
            "prompt_tokens": 80,
            "completion_tokens": 20,
        },
    ]

    summary = summarize_results(rows)
    assert summary["head_to_head"]["wins_pipeline"] == 1
    assert summary["head_to_head"]["wins_single_pass"] == 0
    assert summary["modes"]["solvita_pipeline"]["avg_prompt_tokens"] == 100.0
    assert summary["modes"]["single_pass"]["avg_completion_tokens"] == 20.0


def test_render_markdown_report_contains_key_sections():
    report = render_markdown_report(
        {
            "modes": {
                "solvita_pipeline": {
                    "count": 1,
                    "compile_success_rate": 1.0,
                    "avg_pass_rate": 0.5,
                    "avg_elapsed_total_s": 2.0,
                    "avg_llm_infer_s": 1.0,
                    "avg_prompt_tokens": 120.0,
                    "avg_completion_tokens": 60.0,
                }
            },
            "head_to_head": {
                "wins_pipeline": 1,
                "wins_single_pass": 0,
                "ties": 0,
            },
        }
    )

    assert "# Benchmark Report" in report
    assert "## Mode Summary" in report
    assert "## Head-to-Head" in report
    assert "avg_prompt_tokens" in report
    assert "avg_completion_tokens" in report
