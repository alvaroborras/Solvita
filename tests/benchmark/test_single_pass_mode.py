from src.benchmark.modes.single_pass import (
    build_single_pass_config,
    build_single_pass_prompt,
    run_single_pass_case,
)


def test_build_single_pass_config_resolves_model():
    cfg = build_single_pass_config({"model": "other-model", "temperature": 0.3})
    # Model is resolved from config/models.yaml roles.generator, not hardcoded
    assert cfg["model"] != "other-model"
    assert cfg["temperature"] == 0.3


def test_single_pass_mode_calls_llm_once(monkeypatch):
    calls = {"n": 0}

    class FakeClient:
        def generate(self, prompt, **kwargs):
            calls["n"] += 1
            return "int main(){return 0;}"

        def get_usage_snapshot(self):
            return {
                "prompt_tokens": 123,
                "completion_tokens": 45,
                "token_usage_source": "api",
            }

    monkeypatch.setattr("src.benchmark.modes.single_pass._resolve_single_pass_model", lambda cfg: "test-model")
    monkeypatch.setattr("src.benchmark.modes.single_pass.UnifiedLLMClient", lambda cfg: FakeClient())
    monkeypatch.setattr("src.benchmark.modes.single_pass.sanitize_cpp", lambda code: code)
    monkeypatch.setattr(
        "src.benchmark.modes.single_pass.score_solution_on_official_tests",
        lambda **kwargs: {
            "compile_success": True,
            "passed_tests": 0,
            "total_tests": 1,
            "pass_rate": 0.0,
            "error": None,
        },
    )

    result = run_single_pass_case(
        problem_payload={
            "problem_id": "p1",
            "raw_problem": {"description": "x", "public_tests": []},
            "official_tests": [{"input": "", "output": ""}],
        },
        config={"model": "gpt-4"},
    )

    assert calls["n"] == 1
    assert result.mode == "single_pass"
    assert result.prompt_tokens == 123
    assert result.completion_tokens == 45
    assert result.token_usage_source == "api"


def test_single_pass_mode_uses_official_tests_for_scoring(monkeypatch):
    captured = {}

    class FakeClient:
        def generate(self, prompt, **kwargs):
            return "int main(){return 0;}"

        def get_usage_snapshot(self):
            return {
                "prompt_tokens": 17,
                "completion_tokens": 9,
                "token_usage_source": "estimated",
            }

    def fake_score_solution_on_official_tests(**kwargs):
        captured.update(kwargs)
        return {
            "compile_success": True,
            "passed_tests": 1,
            "total_tests": 2,
            "pass_rate": 0.5,
            "error": None,
        }

    monkeypatch.setattr("src.benchmark.modes.single_pass._resolve_single_pass_model", lambda cfg: "test-model")
    monkeypatch.setattr("src.benchmark.modes.single_pass.UnifiedLLMClient", lambda cfg: FakeClient())
    monkeypatch.setattr("src.benchmark.modes.single_pass.sanitize_cpp", lambda code: code)
    monkeypatch.setattr(
        "src.benchmark.modes.single_pass.score_solution_on_official_tests",
        fake_score_solution_on_official_tests,
    )

    result = run_single_pass_case(
        problem_payload={
            "problem_id": "p2",
            "raw_problem": {"description": "x", "public_tests": []},
            "official_tests": [{"input": "a", "output": "b"}, {"input": "c", "output": "d"}],
        }
    )

    assert captured["official_tests"] == [{"input": "a", "output": "b"}, {"input": "c", "output": "d"}]
    assert result.passed_tests == 1
    assert result.total_tests == 2
    assert result.prompt_tokens == 17
    assert result.completion_tokens == 9


def test_single_pass_mode_returns_error_on_empty_response(monkeypatch):
    class FakeClient:
        def generate(self, prompt, **kwargs):
            return ""

        def get_usage_snapshot(self):
            return {
                "prompt_tokens": 11,
                "completion_tokens": 0,
                "token_usage_source": "api",
            }

    monkeypatch.setattr("src.benchmark.modes.single_pass._resolve_single_pass_model", lambda cfg: "test-model")
    monkeypatch.setattr("src.benchmark.modes.single_pass.UnifiedLLMClient", lambda cfg: FakeClient())

    result = run_single_pass_case(
        problem_payload={
            "problem_id": "p3",
            "raw_problem": {"description": "x", "public_tests": []},
            "official_tests": [{"input": "", "output": ""}],
        }
    )

    assert result.status == "error"
    assert result.error == "Empty model response"
    assert result.prompt_tokens == 11


def test_build_single_pass_prompt_includes_problem_and_samples():
    prompt = build_single_pass_prompt(
        {
            "description": "solve it",
            "time_limit": 2000,
            "space_limit": 256,
            "public_tests": [{"input": "1\n", "output": "2\n"}],
        }
    )

    assert "solve it" in prompt
    assert "2000 ms" in prompt
    assert "256 MB" in prompt
    assert "Sample 1 Input" in prompt
