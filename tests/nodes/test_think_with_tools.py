"""Sub-A: think turn Python tool use via <run_python> markdown blocks."""
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


def _make_state(extra=None):
    from src.graph.state import create_initial_state
    cfg = {"max_iterations": 5, "codegen": {"multi_turn_initial": True}}
    if extra:
        cfg["codegen"].update(extra)
    st = create_initial_state(
        {"description": "d", "public_tests": []},
        cfg,
    )
    st["problem"]["canonical"] = {"objective": "o"}
    st["plan"]["algorithm_choice"] = "a"
    st["plan"]["implementation_steps"] = ["s"]
    return st


def test_extract_run_python_blocks_finds_single():
    from src.nodes.generate_code import _extract_run_python_blocks
    txt = "Algorithm: foo\n<run_python>\nprint(1+1)\n</run_python>\nDone"
    assert _extract_run_python_blocks(txt) == ["print(1+1)"]


def test_extract_run_python_blocks_finds_multiple():
    from src.nodes.generate_code import _extract_run_python_blocks
    txt = "<run_python>print(1)</run_python> middle <run_python>\nprint(2)\nprint(3)\n</run_python>"
    assert _extract_run_python_blocks(txt) == ["print(1)", "print(2)\nprint(3)"]


def test_extract_run_python_blocks_no_blocks():
    from src.nodes.generate_code import _extract_run_python_blocks
    assert _extract_run_python_blocks("just text") == []
    assert _extract_run_python_blocks("") == []


def test_extract_run_python_blocks_case_insensitive():
    from src.nodes.generate_code import _extract_run_python_blocks
    assert _extract_run_python_blocks("<RUN_PYTHON>print(1)</RUN_PYTHON>") == ["print(1)"]


def test_format_python_tool_results_includes_outputs():
    from src.nodes.generate_code import _format_python_tool_results
    out = _format_python_tool_results(
        ["print(2)"],
        [(0, "2\n", "")],
    )
    assert "Block 1" in out
    assert "stdout:\n2" in out
    assert "exit_code=0" in out


def test_format_python_tool_results_handles_stderr_and_no_output():
    from src.nodes.generate_code import _format_python_tool_results
    out = _format_python_tool_results(
        ["pass", "1/0"],
        [(0, "", ""), (1, "", "ZeroDivisionError")],
    )
    assert "(no output)" in out
    assert "ZeroDivisionError" in out


def test_execute_think_python_tools_no_blocks_returns_immediately(monkeypatch):
    """If response has no <run_python>, no extra LLM calls."""
    from src.nodes import generate_code as gc

    def boom(*a, **k):
        raise AssertionError("chat_with_history should not be called")

    monkeypatch.setattr(gc, "chat_with_history", boom)

    final, new, persisted, n_calls, _blocks = gc._execute_think_python_tools(
        llm=None,
        initial_response="just an algorithm. VERDICT: PROCEED",
        history=[{"role": "user", "content": "x"}],
    )

    assert final == "just an algorithm. VERDICT: PROCEED"
    assert new == []
    assert n_calls == 0
    assert persisted == [{"role": "user", "content": "x"}]


def test_execute_think_python_tools_runs_one_block_then_stops(monkeypatch):
    """LLM emits one block; result fed back; second response has no block → stop."""
    from src.nodes import generate_code as gc

    captured_user_msgs = []

    def fake_chat(llm, hist, *, user_content, **kwargs):
        captured_user_msgs.append(user_content)
        new_msgs = [
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": "now I see, VERDICT: PROCEED"},
        ]
        return "now I see, VERDICT: PROCEED", new_msgs, list(hist) + new_msgs

    monkeypatch.setattr(gc, "chat_with_history", fake_chat)
    monkeypatch.setattr(gc, "run_python", lambda block, **k: (0, "42\n", ""))

    initial = "Trying algo:\n<run_python>print(2*21)</run_python>\nthinking..."
    final, new, persisted, n_calls, _blocks = gc._execute_think_python_tools(
        llm=object(),
        initial_response=initial,
        history=[{"role": "user", "content": "init"}],
    )

    assert n_calls == 1
    assert "VERDICT: PROCEED" in final
    assert any("42" in m for m in captured_user_msgs)


def test_execute_think_python_tools_caps_at_max_iters(monkeypatch):
    """If LLM keeps emitting blocks, stop after max_iters."""
    from src.nodes import generate_code as gc

    chat_calls = {"n": 0}

    def fake_chat(llm, hist, *, user_content, **kwargs):
        chat_calls["n"] += 1
        # always re-emit a block
        new_msgs = [
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": "<run_python>print(1)</run_python> still going"},
        ]
        return "<run_python>print(1)</run_python> still going", new_msgs, list(hist) + new_msgs

    monkeypatch.setattr(gc, "chat_with_history", fake_chat)
    monkeypatch.setattr(gc, "run_python", lambda block, **k: (0, "1\n", ""))

    initial = "<run_python>print(1)</run_python>"
    final, new, persisted, n_calls, _blocks = gc._execute_think_python_tools(
        llm=object(),
        initial_response=initial,
        history=[],
        max_iters=3,
    )

    assert n_calls == 3
    assert chat_calls["n"] == 3


def test_think_with_tools_integrated_path(monkeypatch):
    """End-to-end: generate_code_node calls think → tool block → continuation → code."""
    from src.nodes import generate_code as gc

    _patch_llm(monkeypatch)
    sequence = {"think": 0, "code": 0}

    def fake_call(_llm, prompt_builder, *args, **kwargs):
        stage = kwargs.get("_stage", "")
        if stage == "generate_code.think":
            sequence["think"] += 1
            return "Idea\n<run_python>print(2)</run_python>\nstill thinking", [], []
        if stage == "generate_code.code_only":
            sequence["code"] += 1
            return "int main(){return 0;}", [], []
        return "", [], []

    chat_calls = {"n": 0}

    def fake_chat(llm, hist, *, user_content, **kwargs):
        chat_calls["n"] += 1
        # First continuation: respond with VERDICT: PROCEED, no more blocks
        return "Confirmed by brute force. VERDICT: PROCEED", [
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": "Confirmed by brute force. VERDICT: PROCEED"},
        ], list(hist) + [
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": "Confirmed by brute force. VERDICT: PROCEED"},
        ]

    monkeypatch.setattr(gc, "_call_generate_with_history", fake_call)
    monkeypatch.setattr(gc, "chat_with_history", fake_chat)
    monkeypatch.setattr(gc, "run_python", lambda block, **k: (0, "2\n", ""))
    monkeypatch.setattr(gc, "_generate_with_compact_retry", lambda *a, **k: ("int main(){return 0;}", [], []))
    monkeypatch.setattr(gc, "_self_validate", lambda *a, **k: (True, [], 0))
    monkeypatch.setattr(gc, "sanitize_cpp", lambda x: x)
    monkeypatch.setattr(gc, "MemoryClient", lambda **kw: _FakeMem())

    gc.generate_code_node(_make_state())

    assert sequence["think"] == 1
    assert sequence["code"] == 1
    assert chat_calls["n"] == 1  # tool result fed back, then VERDICT: PROCEED


def test_think_python_tools_disabled_skips_loop(monkeypatch):
    """Config codegen.think_python_tools=False prevents tool-use even when blocks present."""
    from src.nodes import generate_code as gc

    _patch_llm(monkeypatch)

    def fake_call(_llm, prompt_builder, *args, **kwargs):
        if kwargs.get("_stage", "") == "generate_code.think":
            return "Idea\n<run_python>print(2)</run_python>\nVERDICT: PROCEED", [], []
        return "int main(){return 0;}", [], []

    def boom(*a, **k):
        raise AssertionError("chat_with_history must NOT be called when tools disabled")

    monkeypatch.setattr(gc, "_call_generate_with_history", fake_call)
    monkeypatch.setattr(gc, "chat_with_history", boom)
    monkeypatch.setattr(gc, "_generate_with_compact_retry", lambda *a, **k: ("int main(){return 0;}", [], []))
    monkeypatch.setattr(gc, "_self_validate", lambda *a, **k: (True, [], 0))
    monkeypatch.setattr(gc, "sanitize_cpp", lambda x: x)
    monkeypatch.setattr(gc, "MemoryClient", lambda **kw: _FakeMem())

    gc.generate_code_node(_make_state(extra={"think_python_tools": False}))


def test_think_python_tools_runs_real_python(monkeypatch):
    """Sanity: actual run_python execution path works end-to-end on a trivial block."""
    from src.nodes import generate_code as gc

    chat_calls = {"n": 0}

    def fake_chat(llm, hist, *, user_content, **kwargs):
        chat_calls["n"] += 1
        return "VERDICT: PROCEED", [], list(hist)

    monkeypatch.setattr(gc, "chat_with_history", fake_chat)

    final, new, persisted, n_calls, _blocks = gc._execute_think_python_tools(
        llm=object(),
        initial_response="<run_python>\nprint('hello world')\n</run_python>",
        history=[],
    )

    assert n_calls == 1
    assert chat_calls["n"] == 1


def test_hard_gate_forces_continuation_when_no_tool_used(monkeypatch):
    """HARD-GATE: PROCEED without prior <run_python> triggers a forced continuation message."""
    from src.nodes import generate_code as gc

    _patch_llm(monkeypatch)
    sequence = {"think": 0, "code": 0, "gate_continuations": 0}
    captured_user_msgs = []

    def fake_call(_llm, prompt_builder, *args, **kwargs):
        stage = kwargs.get("_stage", "")
        if stage == "generate_code.think":
            sequence["think"] += 1
            return "Quick algo, no tool used. VERDICT: PROCEED", [], []
        if stage == "generate_code.code_only":
            sequence["code"] += 1
            return "int main(){return 0;}", [], []
        return "", [], []

    def fake_chat(llm, hist, *, user_content, **kwargs):
        captured_user_msgs.append(user_content)
        sequence["gate_continuations"] += 1
        # gate response uses a tool block then declares PROCEED
        return (
            "<run_python>print(42)</run_python>\nNow verified. VERDICT: PROCEED",
            [
                {"role": "user", "content": user_content},
                {"role": "assistant", "content": "<run_python>print(42)</run_python>\nNow verified. VERDICT: PROCEED"},
            ],
            list(hist),
        )

    monkeypatch.setattr(gc, "_call_generate_with_history", fake_call)
    monkeypatch.setattr(gc, "chat_with_history", fake_chat)
    monkeypatch.setattr(gc, "run_python", lambda block, **k: (0, "42\n", ""))
    monkeypatch.setattr(gc, "_generate_with_compact_retry", lambda *a, **k: ("int main(){return 0;}", [], []))
    monkeypatch.setattr(gc, "_self_validate", lambda *a, **k: (True, [], 0))
    monkeypatch.setattr(gc, "sanitize_cpp", lambda x: x)
    monkeypatch.setattr(gc, "MemoryClient", lambda **kw: _FakeMem())

    gc.generate_code_node(_make_state(extra={"think_require_python_tool": True}))

    # think called once, then HARD-GATE forces a continuation that includes a tool block
    assert sequence["think"] == 1
    assert sequence["gate_continuations"] >= 1
    # The forced continuation message must explicitly demand a tool block
    assert any("HARD-GATE" in m or "did not run any" in m for m in captured_user_msgs)


def test_hard_gate_disabled_passes_through_without_tool(monkeypatch):
    """When think_require_python_tool=False, PROCEED is accepted even without a tool block."""
    from src.nodes import generate_code as gc

    _patch_llm(monkeypatch)
    chat_calls = {"n": 0}

    def fake_call(_llm, prompt_builder, *args, **kwargs):
        if kwargs.get("_stage", "") == "generate_code.think":
            return "Quick algo. VERDICT: PROCEED", [], []
        return "int main(){return 0;}", [], []

    def fake_chat(*a, **k):
        chat_calls["n"] += 1
        raise AssertionError("HARD-GATE should not fire when disabled")

    monkeypatch.setattr(gc, "_call_generate_with_history", fake_call)
    monkeypatch.setattr(gc, "chat_with_history", fake_chat)
    monkeypatch.setattr(gc, "_generate_with_compact_retry", lambda *a, **k: ("int main(){return 0;}", [], []))
    monkeypatch.setattr(gc, "_self_validate", lambda *a, **k: (True, [], 0))
    monkeypatch.setattr(gc, "sanitize_cpp", lambda x: x)
    monkeypatch.setattr(gc, "MemoryClient", lambda **kw: _FakeMem())

    gc.generate_code_node(_make_state(extra={"think_require_python_tool": False}))
    assert chat_calls["n"] == 0


def test_hard_gate_block_in_prompt_when_required():
    from src.nodes.generate_code import _build_think_prompt

    p_with = _build_think_prompt(
        problem_desc="x", algorithm="", steps=[], constraints={}, public_tests=[],
        require_python_tool=True,
    )
    assert "HARD-GATE" in p_with

    p_without = _build_think_prompt(
        problem_desc="x", algorithm="", steps=[], constraints={}, public_tests=[],
        require_python_tool=False,
    )
    assert "HARD-GATE" not in p_without
