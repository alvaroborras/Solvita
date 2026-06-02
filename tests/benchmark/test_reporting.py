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
    assert summary["modes"]["solvita_pipeline"]["row_count"] == 1
    assert summary["modes"]["solvita_pipeline"]["problem_count"] == 1
    assert summary["modes"]["single_pass"]["avg_completion_tokens"] == 20.0
    assert summary["modes"]["solvita_pipeline"]["false_accept_rate"] == 0.0
    assert summary["modes"]["solvita_pipeline"]["verifier_accept_rate"] == 0.0
    assert summary["modes"]["solvita_pipeline"]["verifier_repair_rate"] == 0.0
    assert summary["modes"]["solvita_pipeline"]["verifier_escalation_rate"] == 0.0
    assert summary["modes"]["solvita_pipeline"]["full_testgen_completion_rate"] == 0.0


def test_summarize_results_computes_pass_at_k():
    rows = [
        {
            "problem_id": "p1",
            "repeat_index": 1,
            "mode": "solvita_pipeline",
            "pass_rate": 0.5,
            "compile_success": True,
            "elapsed_total_s": 2.0,
            "llm_infer_s": 1.0,
            "prompt_tokens": 100,
            "completion_tokens": 40,
        },
        {
            "problem_id": "p1",
            "repeat_index": 2,
            "mode": "solvita_pipeline",
            "pass_rate": 1.0,
            "compile_success": True,
            "elapsed_total_s": 2.1,
            "llm_infer_s": 1.1,
            "prompt_tokens": 110,
            "completion_tokens": 45,
        },
        {
            "problem_id": "p1",
            "repeat_index": 3,
            "mode": "solvita_pipeline",
            "pass_rate": 0.2,
            "compile_success": True,
            "elapsed_total_s": 2.2,
            "llm_infer_s": 1.2,
            "prompt_tokens": 120,
            "completion_tokens": 50,
        },
        {
            "problem_id": "p2",
            "repeat_index": 1,
            "mode": "solvita_pipeline",
            "pass_rate": 0.0,
            "compile_success": False,
            "elapsed_total_s": 3.0,
            "llm_infer_s": 1.5,
            "prompt_tokens": 130,
            "completion_tokens": 55,
        },
        {
            "problem_id": "p2",
            "repeat_index": 2,
            "mode": "solvita_pipeline",
            "pass_rate": 0.7,
            "compile_success": True,
            "elapsed_total_s": 3.1,
            "llm_infer_s": 1.6,
            "prompt_tokens": 140,
            "completion_tokens": 60,
        },
        {
            "problem_id": "p2",
            "repeat_index": 3,
            "mode": "solvita_pipeline",
            "pass_rate": 0.4,
            "compile_success": True,
            "elapsed_total_s": 3.2,
            "llm_infer_s": 1.7,
            "prompt_tokens": 150,
            "completion_tokens": 65,
        },
    ]

    summary = summarize_results(rows, repeats=3)
    stats = summary["pass_at_k"]["solvita_pipeline"]

    assert stats["k"] == 3
    assert stats["problem_count"] == 2
    assert stats["full_pass_at_1"] == 0
    assert stats["full_pass_at_k"] == 1
    assert stats["full_pass_at_1_rate"] == 0.0
    assert stats["full_pass_at_k_rate"] == 0.5
    assert stats["avg_pass_rate_at_1"] == 0.25
    assert stats["avg_best_of_k_pass_rate"] == 0.85
def test_render_markdown_report_contains_key_sections():
    report = render_markdown_report(
        {
            "modes": {
                "solvita_pipeline": {
                    "row_count": 1,
                    "problem_count": 1,
                    "compile_success_rate": 1.0,
                    "avg_pass_rate": 0.5,
                    "avg_elapsed_total_s": 2.0,
                    "avg_llm_infer_s": 1.0,
                    "avg_prompt_tokens": 120.0,
                    "avg_completion_tokens": 60.0,
                    "false_accept_rate": 0.0,
                    "verifier_accept_rate": 1.0,
                    "verifier_repair_rate": 0.0,
                    "verifier_escalation_rate": 0.0,
                    "full_testgen_completion_rate": 1.0,
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
    assert "false_accept_rate" in report
    assert "verifier_accept_rate" in report
    assert "full_testgen_completion_rate" in report
