"""Sub-B: think VERDICT parsing + redesign retry loop."""
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


def _make_state(extra_codegen=None):
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
    return st


def test_parse_verdict_proceed():
    from src.nodes.generate_code import _parse_think_verdict
    v = _parse_think_verdict("blah blah\n\nVERDICT: PROCEED")
    assert v == {"proceed": True, "reason": ""}


def test_parse_verdict_redesign_with_reason():
    from src.nodes.generate_code import _parse_think_verdict
    v = _parse_think_verdict("blah\n\nVERDICT: REDESIGN_NEEDED — complexity exceeds 10^9")
    assert v["proceed"] is False
    assert "complexity exceeds" in v["reason"]


def test_parse_verdict_redesign_with_dash():
    from src.nodes.generate_code import _parse_think_verdict
    v = _parse_think_verdict("blah\n\nVERDICT: REDESIGN_NEEDED - bad formula")
    assert v["proceed"] is False
    assert "bad formula" in v["reason"]


def test_parse_verdict_missing_defaults_to_proceed():
    """Backward-compat: no VERDICT line → proceed."""
    from src.nodes.generate_code import _parse_think_verdict
    v = _parse_think_verdict("just an algorithm description")
    assert v["proceed"] is True


def test_parse_verdict_case_insensitive():
    from src.nodes.generate_code import _parse_think_verdict
    v = _parse_think_verdict("verdict: redesign_needed — try again")
    assert v["proceed"] is False


def test_redesign_loop_retries_then_proceeds(monkeypatch):
    """First think says REDESIGN_NEEDED, second says PROCEED → 2 think turns."""
    from src.nodes import generate_code as gc

    _patch_llm(monkeypatch)
    think_calls = {"n": 0}
    redesign_feedback_seen = []

    def fake_call(_llm, prompt_builder, *args, **kwargs):
        stage = kwargs.get("_stage", "")
        if stage == "generate_code.think":
            think_calls["n"] += 1
            redesign_feedback_seen.append(kwargs.get("redesign_feedback", ""))
            if think_calls["n"] == 1:
                return "Algorithm idea\n\nVERDICT: REDESIGN_NEEDED — complexity 10^10 too slow", [], []
            return "Better algorithm\n\nVERDICT: PROCEED", [], []
        return "int main(){return 0;}", [], []

    monkeypatch.setattr(gc, "_call_generate_with_history", fake_call)
    monkeypatch.setattr(gc, "_generate_with_compact_retry", lambda *a, **k: ("int main(){return 0;}", [], []))
    monkeypatch.setattr(gc, "_self_validate", lambda *a, **k: (True, [], 0))
    monkeypatch.setattr(gc, "sanitize_cpp", lambda x: x)
    monkeypatch.setattr(gc, "MemoryClient", lambda **kw: _FakeMem())

    gc.generate_code_node(_make_state())

    assert think_calls["n"] == 2
    assert redesign_feedback_seen[0] == ""  # first attempt has no feedback
    assert "10^10" in redesign_feedback_seen[1]  # second attempt sees the prior reason


def test_redesign_loop_caps_at_max_attempts(monkeypatch):
    """Always REDESIGN_NEEDED → caps at think_max_attempts (3 by default), proceeds anyway."""
    from src.nodes import generate_code as gc

    _patch_llm(monkeypatch)
    think_calls = {"n": 0}

    def fake_call(_llm, prompt_builder, *args, **kwargs):
        stage = kwargs.get("_stage", "")
        if stage == "generate_code.think":
            think_calls["n"] += 1
            return "stuck\n\nVERDICT: REDESIGN_NEEDED — same problem", [], []
        return "int main(){return 0;}", [], []

    monkeypatch.setattr(gc, "_call_generate_with_history", fake_call)
    monkeypatch.setattr(gc, "_generate_with_compact_retry", lambda *a, **k: ("int main(){return 0;}", [], []))
    monkeypatch.setattr(gc, "_self_validate", lambda *a, **k: (True, [], 0))
    monkeypatch.setattr(gc, "sanitize_cpp", lambda x: x)
    monkeypatch.setattr(gc, "MemoryClient", lambda **kw: _FakeMem())

    gc.generate_code_node(_make_state())

    assert think_calls["n"] == 3  # default max_attempts


def test_redesign_loop_respects_config_override(monkeypatch):
    """think_max_attempts=2 means up to 2 think calls."""
    from src.nodes import generate_code as gc

    _patch_llm(monkeypatch)
    think_calls = {"n": 0}

    def fake_call(_llm, prompt_builder, *args, **kwargs):
        if kwargs.get("_stage", "") == "generate_code.think":
            think_calls["n"] += 1
            return "VERDICT: REDESIGN_NEEDED — never satisfied", [], []
        return "int main(){return 0;}", [], []

    monkeypatch.setattr(gc, "_call_generate_with_history", fake_call)
    monkeypatch.setattr(gc, "_generate_with_compact_retry", lambda *a, **k: ("int main(){return 0;}", [], []))
    monkeypatch.setattr(gc, "_self_validate", lambda *a, **k: (True, [], 0))
    monkeypatch.setattr(gc, "sanitize_cpp", lambda x: x)
    monkeypatch.setattr(gc, "MemoryClient", lambda **kw: _FakeMem())

    gc.generate_code_node(_make_state(extra_codegen={"think_max_attempts": 2}))

    assert think_calls["n"] == 2


def test_redesign_loop_proceeds_immediately_on_first_proceed(monkeypatch):
    """First VERDICT: PROCEED → only 1 think turn."""
    from src.nodes import generate_code as gc

    _patch_llm(monkeypatch)
    think_calls = {"n": 0}

    def fake_call(_llm, prompt_builder, *args, **kwargs):
        if kwargs.get("_stage", "") == "generate_code.think":
            think_calls["n"] += 1
            return "Good algo\n\nVERDICT: PROCEED", [], []
        return "int main(){return 0;}", [], []

    monkeypatch.setattr(gc, "_call_generate_with_history", fake_call)
    monkeypatch.setattr(gc, "_generate_with_compact_retry", lambda *a, **k: ("int main(){return 0;}", [], []))
    monkeypatch.setattr(gc, "_self_validate", lambda *a, **k: (True, [], 0))
    monkeypatch.setattr(gc, "sanitize_cpp", lambda x: x)
    monkeypatch.setattr(gc, "MemoryClient", lambda **kw: _FakeMem())

    gc.generate_code_node(_make_state())

    assert think_calls["n"] == 1


def test_think_prompt_renders_redesign_feedback():
    from src.nodes.generate_code import _build_think_prompt

    prompt = _build_think_prompt(
        problem_desc="x",
        algorithm="",
        steps=[],
        constraints={},
        public_tests=[],
        redesign_feedback="prior attempt was O(n^3), too slow",
    )
    assert "REDESIGN FEEDBACK" in prompt
    assert "O(n^3)" in prompt
