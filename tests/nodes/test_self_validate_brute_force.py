"""Sub-D: cross-validation against Python brute force oracle."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


class _FakeMem:
    def get_injection(self, **kwargs):
        return "", []


class _FakeLLMClient:
    @staticmethod
    def build_role_config(*a, **k):
        return {}

    def __init__(self, cfg):
        pass


def _patch_llm(monkeypatch):
    import src.nodes.generate_code as gc
    monkeypatch.setattr(gc, "UnifiedLLMClient", _FakeLLMClient)


def _make_state(*, oracle_status="ok", extra_codegen=None):
    from src.graph.state import create_initial_state
    cfg = {"max_iterations": 5, "codegen": {"multi_turn_initial": True, "think_require_python_tool": False}}
    if extra_codegen:
        cfg["codegen"].update(extra_codegen)
    st = create_initial_state(
        {"description": "d", "public_tests": []},
        cfg,
    )
    st["problem"]["canonical"] = {"objective": "o"}
    st["plan"]["algorithm_choice"] = "a"
    st["plan"]["implementation_steps"] = ["s"]
    st["tests"]["oracle_status"] = oracle_status
    return st


def test_parse_python_oracle_response_valid_json():
    from src.nodes.generate_code import _parse_python_oracle_response
    raw = '{"brute_force": "print(1)", "input_generator": "print(\\"x\\")"}'
    parsed = _parse_python_oracle_response(raw)
    assert parsed == {"brute_force": "print(1)", "input_generator": 'print("x")'}


def test_parse_python_oracle_response_with_markdown_fence():
    from src.nodes.generate_code import _parse_python_oracle_response
    raw = '```json\n{"brute_force": "print(1)", "input_generator": "print(2)"}\n```'
    parsed = _parse_python_oracle_response(raw)
    assert parsed["brute_force"] == "print(1)"


def test_parse_python_oracle_response_with_prose_around_json():
    from src.nodes.generate_code import _parse_python_oracle_response
    raw = 'Here is my answer:\n{"brute_force": "print(7)", "input_generator": "print(8)"}\nHope this helps.'
    parsed = _parse_python_oracle_response(raw)
    assert parsed["brute_force"] == "print(7)"


def test_parse_python_oracle_response_invalid():
    from src.nodes.generate_code import _parse_python_oracle_response
    assert _parse_python_oracle_response("not json") is None
    assert _parse_python_oracle_response("") is None
    assert _parse_python_oracle_response('{"brute_force": "p"}') is None  # missing key


def test_python_oracle_prompt_includes_constraints_block():
    from src.nodes.generate_code import _build_python_oracle_prompt
    p = _build_python_oracle_prompt(
        problem_desc="x",
        constraints={"n": "up to 100"},
        public_tests=[{"input": "1", "output": "1"}],
    )
    assert "n" in p
    assert "Sample 1" in p
    assert "brute_force" in p
    assert "input_generator" in p


def test_run_python_with_stdin_round_trip():
    """Sanity: feed input via stdin to a Python script and read the result back."""
    from src.nodes.generate_code import _run_python_with_stdin
    script = "import sys\nn = int(sys.stdin.read().strip())\nprint(n * 2)"
    ret, stdout, stderr = _run_python_with_stdin(script, "21\n")
    assert ret == 0
    assert stdout.strip() == "42"


def test_run_brute_force_comparison_no_mismatch(monkeypatch, tmp_path):
    """When C++ output matches brute force, no failures recorded."""
    from src.nodes import generate_code as gc

    # mock both Python runners and run_program to return same output
    monkeypatch.setattr(gc, "run_python", lambda script, **k: (0, "5\n", ""))
    monkeypatch.setattr(gc, "_run_python_with_stdin", lambda script, stdin: (0, "10\n", ""))
    monkeypatch.setattr(gc, "run_program", lambda exe, input_text, limits=None: (0, "10\n", ""))

    failures = gc._run_brute_force_comparison(
        cpp_exe_path=tmp_path / "fake.exe",
        brute_force_script="print(int(input())*2)",
        input_generator_script="print(5)",
        n_random=3,
    )
    assert failures == []


def test_run_brute_force_comparison_detects_mismatch(monkeypatch, tmp_path):
    """When C++ disagrees with brute force, mismatch failure recorded."""
    from src.nodes import generate_code as gc

    monkeypatch.setattr(gc, "run_python", lambda script, **k: (0, "5\n", ""))
    monkeypatch.setattr(gc, "_run_python_with_stdin", lambda script, stdin: (0, "10\n", ""))  # brute says 10
    monkeypatch.setattr(gc, "run_program", lambda exe, input_text, limits=None: (0, "11\n", ""))  # C++ says 11

    failures = gc._run_brute_force_comparison(
        cpp_exe_path=tmp_path / "fake.exe",
        brute_force_script="print(int(input())*2)",
        input_generator_script="print(5)",
        n_random=3,
    )
    assert len(failures) == 3
    assert all(f["type"] == "brute_force_mismatch" for f in failures)
    assert failures[0]["expected"] == "10"
    assert failures[0]["actual"] == "11"


def test_run_brute_force_comparison_skips_when_generator_broken(monkeypatch, tmp_path):
    """If input_generator returns non-zero, no failures (graceful skip)."""
    from src.nodes import generate_code as gc

    monkeypatch.setattr(gc, "run_python", lambda script, **k: (1, "", "broken"))

    failures = gc._run_brute_force_comparison(
        cpp_exe_path=tmp_path / "fake.exe",
        brute_force_script="print(1)",
        input_generator_script="raise NameError",
        n_random=3,
    )
    assert failures == []


def test_self_validate_passes_brute_force_kwargs_through(monkeypatch):
    """_self_validate forwards brute_force_script + input_generator_script to comparator."""
    from src.nodes import generate_code as gc

    captured = {}

    def fake_compile(*a, **k):
        return True, ""

    def fake_run_program(*a, **k):
        return 0, "ok\n", ""

    def fake_brute_force(cpp_exe_path, brute_force_script, input_generator_script, n_random, **k):
        captured["bf"] = brute_force_script
        captured["gen"] = input_generator_script
        captured["n"] = n_random
        return []

    monkeypatch.setattr(gc, "compile_cpp", fake_compile)
    monkeypatch.setattr(gc, "run_program", fake_run_program)
    monkeypatch.setattr(gc, "_run_brute_force_comparison", fake_brute_force)
    monkeypatch.setattr(gc, "judge_output_against_certified_expected", lambda **k: (True, None))

    passed, failures, _ = gc._self_validate(
        "int main(){return 0;}",
        [{"id": "p_0", "input": "1\n", "expected_output": "ok"}],
        brute_force_script="bf script",
        input_generator_script="gen script",
        n_random=10,
    )
    assert passed is True
    assert captured == {"bf": "bf script", "gen": "gen script", "n": 10}


def test_generate_code_calls_python_oracle_when_oracle_failed(monkeypatch):
    """When oracle_status='failed' and cross_validation enabled, _build_python_oracle_prompt is invoked."""
    from src.nodes import generate_code as gc

    _patch_llm(monkeypatch)
    seen_stages = []

    def fake_call(_llm, prompt_builder, *args, **kwargs):
        stage = kwargs.get("_stage", "")
        seen_stages.append(stage)
        if stage == "generate_code.python_oracle":
            return '{"brute_force": "print(1)", "input_generator": "print(2)"}', [], []
        return "int main(){return 0;}", [], []

    monkeypatch.setattr(gc, "_call_generate_with_history", fake_call)
    monkeypatch.setattr(gc, "_generate_with_compact_retry", lambda *a, **k: ("int main(){return 0;}", [], []))
    monkeypatch.setattr(gc, "_self_validate", lambda *a, **k: (True, [], 0))
    monkeypatch.setattr(gc, "sanitize_cpp", lambda x: x)
    monkeypatch.setattr(gc, "MemoryClient", lambda **kw: _FakeMem())

    gc.generate_code_node(_make_state(oracle_status="failed"))

    assert "generate_code.python_oracle" in seen_stages


def test_generate_code_skips_python_oracle_when_tdd_disabled(monkeypatch):
    """When tdd_enabled=False, the python_oracle stage is not invoked."""
    from src.nodes import generate_code as gc

    _patch_llm(monkeypatch)
    seen_stages = []

    def fake_call(_llm, prompt_builder, *args, **kwargs):
        seen_stages.append(kwargs.get("_stage", ""))
        return "int main(){return 0;}", [], []

    monkeypatch.setattr(gc, "_call_generate_with_history", fake_call)
    monkeypatch.setattr(gc, "_generate_with_compact_retry", lambda *a, **k: ("int main(){return 0;}", [], []))
    monkeypatch.setattr(gc, "_self_validate", lambda *a, **k: (True, [], 0))
    monkeypatch.setattr(gc, "sanitize_cpp", lambda x: x)
    monkeypatch.setattr(gc, "MemoryClient", lambda **kw: _FakeMem())

    gc.generate_code_node(_make_state(oracle_status="ok", extra_codegen={"tdd_enabled": False}))

    assert "generate_code.python_oracle" not in seen_stages


def test_generate_code_python_oracle_runs_when_cross_validation_always(monkeypatch):
    """cross_validation_always=True forces oracle generation even when oracle_status=ok."""
    from src.nodes import generate_code as gc

    _patch_llm(monkeypatch)
    seen_stages = []

    def fake_call(_llm, prompt_builder, *args, **kwargs):
        stage = kwargs.get("_stage", "")
        seen_stages.append(stage)
        if stage == "generate_code.python_oracle":
            return '{"brute_force": "print(1)", "input_generator": "print(2)"}', [], []
        return "int main(){return 0;}", [], []

    monkeypatch.setattr(gc, "_call_generate_with_history", fake_call)
    monkeypatch.setattr(gc, "_generate_with_compact_retry", lambda *a, **k: ("int main(){return 0;}", [], []))
    monkeypatch.setattr(gc, "_self_validate", lambda *a, **k: (True, [], 0))
    monkeypatch.setattr(gc, "sanitize_cpp", lambda x: x)
    monkeypatch.setattr(gc, "MemoryClient", lambda **kw: _FakeMem())

    gc.generate_code_node(_make_state(oracle_status="ok", extra_codegen={"cross_validation_always": True}))

    assert "generate_code.python_oracle" in seen_stages


def test_generate_code_disables_oracle_with_cross_validation_false(monkeypatch):
    """cross_validation=False disables oracle generation entirely."""
    from src.nodes import generate_code as gc

    _patch_llm(monkeypatch)
    seen_stages = []

    def fake_call(_llm, prompt_builder, *args, **kwargs):
        seen_stages.append(kwargs.get("_stage", ""))
        return "int main(){return 0;}", [], []

    monkeypatch.setattr(gc, "_call_generate_with_history", fake_call)
    monkeypatch.setattr(gc, "_generate_with_compact_retry", lambda *a, **k: ("int main(){return 0;}", [], []))
    monkeypatch.setattr(gc, "_self_validate", lambda *a, **k: (True, [], 0))
    monkeypatch.setattr(gc, "sanitize_cpp", lambda x: x)
    monkeypatch.setattr(gc, "MemoryClient", lambda **kw: _FakeMem())

    gc.generate_code_node(_make_state(oracle_status="failed", extra_codegen={"cross_validation": False}))

    assert "generate_code.python_oracle" not in seen_stages
