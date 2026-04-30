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


def _make_state(multi_turn=True):
    from src.graph.state import create_initial_state

    st = create_initial_state(
        {"description": "d", "public_tests": []},
        {
            "max_iterations": 5,
            "codegen": {
                "multi_turn_initial": multi_turn,
                "think_require_python_tool": False,
                "tdd_enabled": False,
            },
        },
    )
    st["problem"]["canonical"] = {"objective": "o"}
    st["plan"]["algorithm_choice"] = "a"
    st["plan"]["implementation_steps"] = ["s"]
    return st


def test_multi_turn_initial_makes_two_llm_calls(monkeypatch):
    """multi_turn_initial=True: think call + code_only call = 2 LLM calls."""
    from src.nodes import generate_code as gc

    _patch_llm(monkeypatch)
    call_stages = []

    def fake_call(_llm, prompt_builder, *args, **kwargs):
        call_stages.append(kwargs.get("_stage", ""))
        return "int main(){return 0;}", [], []

    monkeypatch.setattr(gc, "_call_generate_with_history", fake_call)
    monkeypatch.setattr(gc, "_generate_with_compact_retry", lambda *a, **k: ("int main(){return 0;}", [], []))
    monkeypatch.setattr(gc, "_self_validate", lambda *a, **k: (True, [], 0))
    monkeypatch.setattr(gc, "sanitize_cpp", lambda x: x)
    monkeypatch.setattr(gc, "MemoryClient", lambda **kw: _FakeMem())

    gc.generate_code_node(_make_state(multi_turn=True))

    assert len(call_stages) == 2
    assert call_stages[0] == "generate_code.think"
    assert call_stages[1] == "generate_code.code_only"


def test_single_turn_initial_makes_one_llm_call(monkeypatch):
    """multi_turn_initial=False: only the initial call, no think call."""
    from src.nodes import generate_code as gc

    _patch_llm(monkeypatch)
    call_stages = []

    def fake_call(_llm, prompt_builder, *args, **kwargs):
        call_stages.append(kwargs.get("_stage", ""))
        return "int main(){return 0;}", [], []

    monkeypatch.setattr(gc, "_call_generate_with_history", fake_call)
    monkeypatch.setattr(gc, "_generate_with_compact_retry", lambda *a, **k: ("int main(){return 0;}", [], []))
    monkeypatch.setattr(gc, "_self_validate", lambda *a, **k: (True, [], 0))
    monkeypatch.setattr(gc, "sanitize_cpp", lambda x: x)
    monkeypatch.setattr(gc, "MemoryClient", lambda **kw: _FakeMem())

    gc.generate_code_node(_make_state(multi_turn=False))

    assert len(call_stages) == 1
    assert call_stages[0] == "generate_code.initial"


def test_multi_turn_think_response_in_history_for_code_call(monkeypatch):
    """The think response must appear in messages_history passed to the code_only call."""
    from src.nodes import generate_code as gc

    _patch_llm(monkeypatch)
    captured_history = {}

    THINK_MSG = {"role": "assistant", "content": "Algorithm design: use DP."}

    def fake_call(_llm, prompt_builder, *args, **kwargs):
        stage = kwargs.get("_stage", "")
        if stage == "generate_code.think":
            # Return a persisted_messages list that includes the think response
            return "Algorithm design: use DP.", [], [THINK_MSG]
        if stage == "generate_code.code_only":
            captured_history["history"] = kwargs.get("messages_history", [])
            return "int main(){return 0;}", [], []
        return "", [], []

    monkeypatch.setattr(gc, "_call_generate_with_history", fake_call)
    monkeypatch.setattr(gc, "_generate_with_compact_retry", lambda *a, **k: ("int main(){return 0;}", [], []))
    monkeypatch.setattr(gc, "_self_validate", lambda *a, **k: (True, [], 0))
    monkeypatch.setattr(gc, "sanitize_cpp", lambda x: x)
    monkeypatch.setattr(gc, "MemoryClient", lambda **kw: _FakeMem())

    gc.generate_code_node(_make_state(multi_turn=True))

    assert len(captured_history["history"]) >= 1
    assert THINK_MSG in captured_history["history"]
