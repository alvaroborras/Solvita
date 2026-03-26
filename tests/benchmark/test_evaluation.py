from pathlib import Path

from src.benchmark.evaluation import score_solution_on_official_tests


def test_score_solution_on_official_tests_uses_only_given_tests(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.benchmark.evaluation.sanitize_cpp",
        lambda code: code,
    )
    monkeypatch.setattr(
        "src.benchmark.evaluation.compile_cpp",
        lambda *a, **k: (True, ""),
    )

    outputs = iter(
        [
            (0, "42\n", ""),
            (0, "41\n", ""),
        ]
    )

    def fake_run_program(*args, **kwargs):
        return next(outputs)

    monkeypatch.setattr("src.benchmark.evaluation.run_program", fake_run_program)

    result = score_solution_on_official_tests(
        code="int main(){}",
        official_tests=[
            {"input": "x", "output": "42\n"},
            {"input": "y", "output": "99\n"},
        ],
    )

    assert result["passed_tests"] == 1
    assert result["total_tests"] == 2
    assert result["pass_rate"] == 0.5


def test_score_solution_on_official_tests_compile_failure(monkeypatch):
    monkeypatch.setattr(
        "src.benchmark.evaluation.sanitize_cpp",
        lambda code: code,
    )
    monkeypatch.setattr(
        "src.benchmark.evaluation.compile_cpp",
        lambda *a, **k: (False, "compile failed"),
    )

    result = score_solution_on_official_tests(
        code="int main(){}",
        official_tests=[{"input": "", "output": ""}],
    )

    assert result["compile_success"] is False
    assert result["passed_tests"] == 0
    assert result["total_tests"] == 1
    assert result["error"] == "compile failed"


def test_score_solution_on_official_tests_reports_runtime_error(monkeypatch):
    monkeypatch.setattr(
        "src.benchmark.evaluation.sanitize_cpp",
        lambda code: code,
    )
    monkeypatch.setattr(
        "src.benchmark.evaluation.compile_cpp",
        lambda *a, **k: (True, ""),
    )
    monkeypatch.setattr(
        "src.benchmark.evaluation.run_program",
        lambda *a, **k: (1, "", "segfault"),
    )

    result = score_solution_on_official_tests(
        code="int main(){}",
        official_tests=[{"input": "x", "output": "42\n"}],
    )

    assert result["compile_success"] is True
    assert result["passed_tests"] == 0
    assert result["total_tests"] == 1
    assert result["error"] == "segfault"


def test_score_solution_on_official_tests_normalizes_trailing_whitespace(monkeypatch):
    monkeypatch.setattr(
        "src.benchmark.evaluation.sanitize_cpp",
        lambda code: code,
    )
    monkeypatch.setattr(
        "src.benchmark.evaluation.compile_cpp",
        lambda *a, **k: (True, ""),
    )
    monkeypatch.setattr(
        "src.benchmark.evaluation.run_program",
        lambda *a, **k: (0, "42   \n", ""),
    )

    result = score_solution_on_official_tests(
        code="int main(){}",
        official_tests=[{"input": "", "output": "42\n"}],
    )

    assert result["compile_success"] is True
    assert result["passed_tests"] == 1
    assert result["pass_rate"] == 1.0
