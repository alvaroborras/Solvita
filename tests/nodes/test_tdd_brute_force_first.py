"""Sub-F: TDD ordering — brute force generated and verified BEFORE C++."""
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


def _make_state(*, public_tests=None, extra_codegen=None):
    from src.graph.state import create_initial_state
    cfg = {"max_iterations": 5, "codegen": {"multi_turn_initial": True, "think_require_python_tool": False}}
    if extra_codegen:
        cfg["codegen"].update(extra_codegen)
    st = create_initial_state(
        {"description": "d", "public_tests": public_tests or []},
        cfg,
    )
    st["problem"]["canonical"] = {"objective": "o"}
    st["plan"]["algorithm_choice"] = "a"
    st["plan"]["implementation_steps"] = ["s"]
    return st


def test_verify_brute_force_on_public_tests_all_pass():
    from src.nodes.generate_code import _verify_brute_force_on_public_tests
    bf = "import sys\nn = int(sys.stdin.read().strip())\nprint(n * 2)"
    tests = [{"input": "5\n", "output": "10"}, {"input": "7\n", "output": "14"}]
    ok, mismatches = _verify_brute_force_on_public_tests(bf, tests)
    assert ok is True
    assert mismatches == []


def test_verify_brute_force_on_public_tests_detects_mismatch():
    from src.nodes.generate_code import _verify_brute_force_on_public_tests
    bf = "import sys\nn = int(sys.stdin.read().strip())\nprint(n + 1)"  # WRONG: should be n*2
    tests = [{"input": "5\n", "output": "10"}]
    ok, mismatches = _verify_brute_force_on_public_tests(bf, tests)
    assert ok is False
    assert len(mismatches) == 1
    assert mismatches[0]["expected"] == "10"
    assert mismatches[0]["actual"] == "6"


def test_verify_brute_force_handles_runtime_error():
    from src.nodes.generate_code import _verify_brute_force_on_public_tests
    bf = "raise NameError('boom')"
    tests = [{"input": "5\n", "output": "10"}]
    ok, mismatches = _verify_brute_force_on_public_tests(bf, tests)
    assert ok is False
    assert "exited with code" in mismatches[0]["message"] or "boom" in mismatches[0].get("message", "")


def test_verify_brute_force_skips_empty_public_inputs():
    from src.nodes.generate_code import _verify_brute_force_on_public_tests
    bf = "print(42)"
    tests = [{"input": "", "output": "42"}]
    ok, mismatches = _verify_brute_force_on_public_tests(bf, tests)
    assert ok is True  # empty inputs are skipped
    assert mismatches == []


def test_format_brute_force_mismatch_feedback_lists_examples():
    from src.nodes.generate_code import _format_brute_force_mismatch_feedback
    feedback = _format_brute_force_mismatch_feedback([
        {"id": "public_0", "input": "abc", "expected": "1", "actual": "2", "message": "off-by-one"},
    ])
    assert "public_0" in feedback
    assert "off-by-one" in feedback or "disagrees" in feedback.lower()


def test_tdd_phase_calls_oracle_then_locks_in_when_brute_force_passes(monkeypatch):
    """Happy path: TDD generates a brute force that matches public tests, locks it in."""
    from src.nodes import generate_code as gc

    _patch_llm(monkeypatch)
    seen_stages = []
    n_oracle = {"calls": 0}

    def fake_call(_llm, prompt_builder, *args, **kwargs):
        stage = kwargs.get("_stage", "")
        seen_stages.append(stage)
        if stage == "generate_code.python_oracle":
            n_oracle["calls"] += 1
            return (
                '{"brute_force": "import sys\\nn = int(sys.stdin.read().strip())\\nprint(n*2)", '
                '"input_generator": "import random\\nprint(random.randint(1,5))"}',
                [], []
            )
        return "int main(){return 0;}", [], []

    self_val_calls = {"bf_received": None}

    def fake_self_validate(code, verify_set, checker_exe=None, **kwargs):
        self_val_calls["bf_received"] = kwargs.get("brute_force_script")
        return True, [], 0

    monkeypatch.setattr(gc, "_call_generate_with_history", fake_call)
    monkeypatch.setattr(gc, "_generate_with_compact_retry", lambda *a, **k: ("int main(){return 0;}", [], []))
    monkeypatch.setattr(gc, "_self_validate", fake_self_validate)
    monkeypatch.setattr(gc, "sanitize_cpp", lambda x: x)
    monkeypatch.setattr(gc, "MemoryClient", lambda **kw: _FakeMem())

    gc.generate_code_node(_make_state(public_tests=[{"input": "5\n", "output": "10"}]))

    assert n_oracle["calls"] == 1
    assert self_val_calls["bf_received"] is not None  # brute force passed to self_validate


def test_tdd_phase_retries_when_brute_force_disagrees(monkeypatch):
    """If first brute force disagrees with public tests, second attempt is requested with feedback."""
    from src.nodes import generate_code as gc

    _patch_llm(monkeypatch)
    n_oracle = {"calls": 0}
    feedbacks_seen = []

    def fake_call(_llm, prompt_builder, *args, **kwargs):
        stage = kwargs.get("_stage", "")
        if stage == "generate_code.python_oracle":
            n_oracle["calls"] += 1
            feedbacks_seen.append(kwargs.get("feedback", ""))
            if n_oracle["calls"] == 1:
                # WRONG brute force: prints n+1 instead of n*2
                return (
                    '{"brute_force": "import sys\\nn = int(sys.stdin.read().strip())\\nprint(n+1)", '
                    '"input_generator": "print(5)"}',
                    [], []
                )
            # CORRECT brute force on retry
            return (
                '{"brute_force": "import sys\\nn = int(sys.stdin.read().strip())\\nprint(n*2)", '
                '"input_generator": "print(5)"}',
                [], []
            )
        return "int main(){return 0;}", [], []

    monkeypatch.setattr(gc, "_call_generate_with_history", fake_call)
    monkeypatch.setattr(gc, "_generate_with_compact_retry", lambda *a, **k: ("int main(){return 0;}", [], []))
    monkeypatch.setattr(gc, "_self_validate", lambda *a, **k: (True, [], 0))
    monkeypatch.setattr(gc, "sanitize_cpp", lambda x: x)
    monkeypatch.setattr(gc, "MemoryClient", lambda **kw: _FakeMem())

    gc.generate_code_node(_make_state(public_tests=[{"input": "5\n", "output": "10"}]))

    assert n_oracle["calls"] == 2
    assert feedbacks_seen[0] == ""  # first attempt has no feedback
    assert "disagrees" in feedbacks_seen[1] or "wrong" in feedbacks_seen[1].lower()


def test_tdd_phase_caps_at_max_attempts(monkeypatch):
    """If brute force never passes, give up after tdd_max_attempts and proceed without oracle."""
    from src.nodes import generate_code as gc

    _patch_llm(monkeypatch)
    n_oracle = {"calls": 0}

    def fake_call(_llm, prompt_builder, *args, **kwargs):
        stage = kwargs.get("_stage", "")
        if stage == "generate_code.python_oracle":
            n_oracle["calls"] += 1
            # always wrong
            return (
                '{"brute_force": "print(99)", "input_generator": "print(1)"}',
                [], []
            )
        return "int main(){return 0;}", [], []

    self_val_calls = {"bf_received": None}

    def fake_self_validate(code, verify_set, checker_exe=None, **kwargs):
        self_val_calls["bf_received"] = kwargs.get("brute_force_script")
        return True, [], 0

    monkeypatch.setattr(gc, "_call_generate_with_history", fake_call)
    monkeypatch.setattr(gc, "_generate_with_compact_retry", lambda *a, **k: ("int main(){return 0;}", [], []))
    monkeypatch.setattr(gc, "_self_validate", fake_self_validate)
    monkeypatch.setattr(gc, "sanitize_cpp", lambda x: x)
    monkeypatch.setattr(gc, "MemoryClient", lambda **kw: _FakeMem())

    gc.generate_code_node(
        _make_state(
            public_tests=[{"input": "5\n", "output": "10"}],
            extra_codegen={"tdd_max_attempts": 2},
        )
    )

    assert n_oracle["calls"] == 2
    assert self_val_calls["bf_received"] is None  # no brute force locked in


def test_tdd_phase_disabled_skips_oracle_call(monkeypatch):
    """tdd_enabled=False: no python_oracle calls."""
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

    gc.generate_code_node(
        _make_state(
            public_tests=[{"input": "5\n", "output": "10"}],
            extra_codegen={"tdd_enabled": False},
        )
    )
    assert "generate_code.python_oracle" not in seen_stages
