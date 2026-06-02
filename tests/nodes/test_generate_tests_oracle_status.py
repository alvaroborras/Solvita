"""Sub-C: TestGen sets state['tests']['oracle_status'] flag.

When all 5 solver_bf attempts fail, oracle_status must be 'failed' so that
downstream CodeGen can warn the LLM that there is no trusted reference.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def test_think_prompt_includes_no_warning_when_oracle_ok():
    """Default oracle_status='ok' produces no warning block."""
    from src.nodes.generate_code import _build_think_prompt

    prompt = _build_think_prompt(
        problem_desc="x",
        algorithm="",
        steps=[],
        constraints={},
        public_tests=[],
        oracle_status="ok",
    )
    assert "automated test generator could not produce" not in prompt
    assert "WARNING" not in prompt or "WARNING" in "(unrelated mention)"


def test_think_prompt_warns_when_oracle_failed():
    """oracle_status='failed' must surface a clear warning to the LLM."""
    from src.nodes.generate_code import _build_think_prompt

    prompt = _build_think_prompt(
        problem_desc="x",
        algorithm="",
        steps=[],
        constraints={},
        public_tests=[],
        oracle_status="failed",
    )
    assert "automated test generator could not produce a reliable" in prompt
    assert "NO trusted oracle" in prompt


def test_generate_code_node_reads_oracle_status_from_state(monkeypatch):
    """generate_code_node passes state['tests']['oracle_status'] into _build_think_prompt."""
    from src.graph.state import create_initial_state
    from src.nodes import generate_code as gc

    captured = {}

    class _FakeLLM:
        @staticmethod
        def build_role_config(*a, **k):
            return {}

        def __init__(self, cfg):
            pass

    def fake_call(_llm, prompt_builder, *args, **kwargs):
        if prompt_builder is gc._build_think_prompt:
            captured["oracle_status"] = kwargs.get("oracle_status")
        return "int main(){return 0;}", [], []

    monkeypatch.setattr(gc, "UnifiedLLMClient", _FakeLLM)
    monkeypatch.setattr(gc, "_call_generate_with_history", fake_call)
    monkeypatch.setattr(gc, "_generate_with_compact_retry", lambda *a, **k: ("int main(){return 0;}", [], []))
    monkeypatch.setattr(gc, "_self_validate", lambda *a, **k: (True, [], 0))
    monkeypatch.setattr(gc, "sanitize_cpp", lambda x: x)

    class _FakeMem:
        def get_injection(self, **kwargs):
            return "", []

    monkeypatch.setattr(gc, "MemoryClient", lambda **kw: _FakeMem())

    st = create_initial_state(
        {"description": "d", "public_tests": []},
        {"max_iterations": 5, "codegen": {"multi_turn_initial": True, "think_require_python_tool": False}},
    )
    st["problem"]["canonical"] = {"objective": "o"}
    st["plan"]["algorithm_choice"] = "a"
    st["plan"]["implementation_steps"] = ["s"]
    st["tests"]["oracle_status"] = "failed"

    gc.generate_code_node(st)

    assert captured["oracle_status"] == "failed"


def test_generate_code_node_defaults_oracle_status_when_missing(monkeypatch):
    """If state['tests']['oracle_status'] is absent, default 'ok' is used."""
    from src.graph.state import create_initial_state
    from src.nodes import generate_code as gc

    captured = {}

    class _FakeLLM:
        @staticmethod
        def build_role_config(*a, **k):
            return {}

        def __init__(self, cfg):
            pass

    def fake_call(_llm, prompt_builder, *args, **kwargs):
        if prompt_builder is gc._build_think_prompt:
            captured["oracle_status"] = kwargs.get("oracle_status")
        return "int main(){return 0;}", [], []

    monkeypatch.setattr(gc, "UnifiedLLMClient", _FakeLLM)
    monkeypatch.setattr(gc, "_call_generate_with_history", fake_call)
    monkeypatch.setattr(gc, "_generate_with_compact_retry", lambda *a, **k: ("int main(){return 0;}", [], []))
    monkeypatch.setattr(gc, "_self_validate", lambda *a, **k: (True, [], 0))
    monkeypatch.setattr(gc, "sanitize_cpp", lambda x: x)

    class _FakeMem:
        def get_injection(self, **kwargs):
            return "", []

    monkeypatch.setattr(gc, "MemoryClient", lambda **kw: _FakeMem())

    st = create_initial_state(
        {"description": "d", "public_tests": []},
        {"max_iterations": 5, "codegen": {"multi_turn_initial": True, "think_require_python_tool": False}},
    )
    st["problem"]["canonical"] = {"objective": "o"}
    st["plan"]["algorithm_choice"] = "a"
    st["plan"]["implementation_steps"] = ["s"]

    gc.generate_code_node(st)

    assert captured["oracle_status"] == "ok"


def test_generate_tests_node_sets_trust_tier_metadata(monkeypatch, tmp_path):
    from src.graph.state import create_initial_state
    from src.nodes import generate_tests as gt

    class _FakeLLM:
        @staticmethod
        def build_role_config(config, role):
            return {}

        def __init__(self, cfg):
            pass

    class _FakeCompletedProcess:
        returncode = 1
        stderr = "generator failed"

    def fake_call(_llm, prompt_builder, *args, **kwargs):
        if prompt_builder is gt.build_generator_prompt:
            return '{"generator_cpp": "int main() { return 0; }"}', [], []
        if prompt_builder is gt.build_validator_prompt:
            return '{"validator_cpp": "int main() { return 0; }"}', [], []
        raise AssertionError(f"unexpected prompt builder: {prompt_builder}")

    def fake_compile_cpp(_src, _exe, include_testlib=False, diagnostic=False):
        return True, ""

    def fake_subprocess_run(*args, **kwargs):
        stdout = kwargs.get("stdout")
        if stdout is not None:
            stdout.write("")
        return _FakeCompletedProcess()

    monkeypatch.setattr(gt, "UnifiedLLMClient", _FakeLLM)
    monkeypatch.setattr(gt, "_call_generate_with_history", fake_call)
    monkeypatch.setattr(gt, "compile_cpp", fake_compile_cpp)
    monkeypatch.setattr(gt.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(gt, "_resolve_data_root", lambda config: tmp_path)

    state = create_initial_state(
        {"description": "demo", "public_tests": [{"input": "1\n", "output": "1\n"}]},
        {},
    )

    update = gt.generate_tests_node(state)

    assert update["tests"]["full_testgen_completed"] is True
    assert update["tests"]["trust_tiers"]["trusted"] >= 1
    assert update["tests"]["trust_tiers"].get("advisory", 0) >= 0
