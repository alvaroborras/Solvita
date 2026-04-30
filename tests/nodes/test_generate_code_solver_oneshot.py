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


def _patch_llm(monkeypatch, gc):
    monkeypatch.setattr(gc, "UnifiedLLMClient", _FakeLLMClient)


def test_initial_codegen_marks_solver_oneshot_spent(monkeypatch):
    from src.graph.state import create_initial_state
    from src.nodes import generate_code as gc

    _patch_llm(monkeypatch, gc)
    monkeypatch.setattr(gc, "build_solver_network_block", lambda s, c: "## graph block")
    monkeypatch.setattr(gc, "_generate_with_compact_retry", lambda *a, **k: ("int main(){return 0;}", [], []))
    monkeypatch.setattr(gc, "_self_validate", lambda *a, **k: (True, [], 0))
    monkeypatch.setattr(gc, "sanitize_cpp", lambda x: x)
    monkeypatch.setattr(gc, "MemoryClient", lambda **kw: _FakeMem())

    st = create_initial_state(
        {"description": "d", "public_tests": []},
        {"max_iterations": 5, "solver_network": {"enabled": True, "graph_dir": "/tmp"},
         "codegen": {"think_require_python_tool": False}},
    )
    st["problem"]["canonical"] = {"objective": "o"}
    st["plan"]["algorithm_choice"] = "a"
    st["plan"]["implementation_steps"] = ["s"]

    out = gc.generate_code_node(st)
    assert out.get("solver_network_oneshot_spent") is True


def test_patch_codegen_does_not_mark_solver_oneshot(monkeypatch):
    from src.graph.state import create_initial_state
    from src.nodes import generate_code as gc

    _patch_llm(monkeypatch, gc)
    calls = {"n": 0}

    def _track(*a, **k):
        calls["n"] += 1
        return ""

    monkeypatch.setattr(gc, "build_solver_network_block", _track)
    monkeypatch.setattr(gc, "_generate_with_compact_retry", lambda *a, **k: ("int main(){return 0;}", [], []))
    monkeypatch.setattr(gc, "_choose_repair_mode", lambda *a, **k: ({"mode": "patch", "confidence": "high", "reason": "localized"}, [], []))
    monkeypatch.setattr(gc, "_self_validate", lambda *a, **k: (True, [], 0))
    monkeypatch.setattr(gc, "sanitize_cpp", lambda x: x)
    monkeypatch.setattr(gc, "MemoryClient", lambda **kw: _FakeMem())

    st = create_initial_state(
        {"description": "d", "public_tests": []},
        {"max_iterations": 5, "solver_network": {"enabled": True, "graph_dir": "/tmp"},
         "codegen": {"think_require_python_tool": False}},
    )
    st["problem"]["canonical"] = {"objective": "o"}
    st["plan"]["algorithm_choice"] = "a"
    st["plan"]["implementation_steps"] = ["s"]
    st["solution"]["code"] = "int main(){return 0;}"
    st["iteration"] = 1

    out = gc.generate_code_node(st)
    assert out.get("solver_network_oneshot_spent") is None
    assert calls["n"] == 0


def test_initial_codegen_retries_with_self_validation_feedback(monkeypatch):
    from src.graph.state import create_initial_state
    from src.nodes import generate_code as gc

    _patch_llm(monkeypatch, gc)
    captured_prompts = []
    validate_calls = {"n": 0}

    def fake_retry(_llm, prompt_builder, *args, **kwargs):
        filtered = {k: v for k, v in kwargs.items() if not k.startswith("_")}
        captured_prompts.append(prompt_builder(*args, compact=False, **filtered))
        return "int main(){return 0;}", [], []

    def fake_self_validate(*args, **kwargs):
        validate_calls["n"] += 1
        if validate_calls["n"] == 1:
            return False, [
                {
                    "id": "public_0",
                    "type": "wrong_answer",
                    "input": "1\n",
                    "expected": "2",
                    "actual": "1",
                    "message": "mismatch",
                }
            ], 1
        return True, [], 1

    monkeypatch.setattr(gc, "_generate_with_compact_retry", fake_retry)
    monkeypatch.setattr(gc, "_choose_repair_mode", lambda *a, **k: ({"mode": "patch", "confidence": "high", "reason": "localized"}, [], []))
    monkeypatch.setattr(gc, "_self_validate", fake_self_validate)
    monkeypatch.setattr(gc, "sanitize_cpp", lambda x: x)
    monkeypatch.setattr(gc, "MemoryClient", lambda **kw: _FakeMem())

    st = create_initial_state(
        {"description": "d", "public_tests": [{"input": "1\n", "output": "2\n"}]},
        {"max_iterations": 5, "codegen": {"multi_turn_initial": False, "tdd_enabled": False}},  # disable multi-turn for this test
    )
    st["problem"]["canonical"] = {"objective": "o"}
    st["plan"]["algorithm_choice"] = "a"
    st["plan"]["implementation_steps"] = ["s"]

    gc.generate_code_node(st)

    assert len(captured_prompts) == 2
    assert "Self-validation failed: 1 issues in 1/1 cases tested:" not in captured_prompts[0]
    assert "Self-validation failed: 1 issues in 1/1 cases tested:" in captured_prompts[1]
    assert "Wrong answer on test public_0:" in captured_prompts[1]
    assert "Expected: 2" in captured_prompts[1]
    assert "Actual:   1" in captured_prompts[1]



def test_patch_codegen_passes_aggregate_failures_into_prompt(monkeypatch):
    from src.graph.state import create_initial_state
    from src.nodes import generate_code as gc

    _patch_llm(monkeypatch, gc)
    captured = {}

    def fake_retry(_llm, prompt_builder, *args, **kwargs):
        if prompt_builder is gc._build_repair_decision_prompt:
            return '{"mode":"patch","confidence":"high","reason":"localized"}', [], []
        filtered = {k: v for k, v in kwargs.items() if not k.startswith("_")}
        captured["prompt"] = prompt_builder(*args, compact=False, **filtered)
        return "<<<<<<< SEARCH\nint main(){return 0;}\n=======\nint main(){return 1;}\n>>>>>>> REPLACE", [], []

    monkeypatch.setattr(gc, "_generate_with_compact_retry", fake_retry)
    monkeypatch.setattr(gc, "_self_validate", lambda *a, **k: (True, [], 0))
    monkeypatch.setattr(gc, "sanitize_cpp", lambda x: x)
    monkeypatch.setattr(gc, "MemoryClient", lambda **kw: _FakeMem())

    st = create_initial_state(
        {"description": "d", "public_tests": []},
        {"max_iterations": 5},
    )
    st["problem"]["canonical"] = {"objective": "o"}
    st["plan"]["algorithm_choice"] = "a"
    st["plan"]["implementation_steps"] = ["s"]
    st["solution"]["code"] = "int main(){return 0;}"
    st["iteration"] = 1
    st["feedback"] = {
        "feedback": {
            "analysis": "many internal mismatches",
            "error_pattern": "logic error",
            "failures": [],
            "aggregate_summary": {
                "total_failed": 70,
                "error_type_counts": {"wrong_answer": 68, "timeout": 2},
                "input_length": {"min": 1, "avg": 12, "max": 50},
                "representative_examples": {},
                "numeric_diff": {},
            },
        },
        "suggested_fixes": ["check edge cases"],
    }

    gc.generate_code_node(st)



def test_patch_codegen_uses_decision_mode_to_choose_regen(monkeypatch):
    from src.graph.state import create_initial_state
    from src.nodes import generate_code as gc

    _patch_llm(monkeypatch, gc)
    calls = {"decision": 0, "regen": 0, "patch": 0}

    monkeypatch.setattr(gc, "MemoryClient", lambda **kw: _FakeMem())
    monkeypatch.setattr(gc, "_self_validate", lambda *a, **k: (True, [], 0))
    monkeypatch.setattr(gc, "sanitize_cpp", lambda x: x)

    def fake_decision(*args, **kwargs):
        calls["decision"] += 1
        return {"mode": "full_regen", "confidence": "high", "reason": "systemic"}, [], []

    def fake_call(_llm, prompt_builder, *args, **kwargs):
        if prompt_builder is gc._build_patch_prompt:
            calls["patch"] += 1
            return "", [], []
        if prompt_builder is gc._build_regenerate_prompt:
            calls["regen"] += 1
            return "int main(){return 0;}", [], []
        raise AssertionError(f"unexpected prompt builder: {prompt_builder}")

    monkeypatch.setattr(gc, "_choose_repair_mode", fake_decision)
    monkeypatch.setattr(gc, "_call_generate_with_history", fake_call)
    monkeypatch.setattr(gc, "_generate_with_compact_retry", lambda *a, **k: ("int main(){return 0;}", [], []))

    st = create_initial_state(
        {"description": "d", "public_tests": []},
        {"max_iterations": 5},
    )
    st["problem"]["canonical"] = {"objective": "o"}
    st["plan"]["algorithm_choice"] = "a"
    st["plan"]["implementation_steps"] = ["s"]
    st["solution"]["code"] = "int main(){return 0;}"
    st["iteration"] = 1
    st["feedback"] = {"feedback": {"failures": [], "aggregate_summary": {}}, "suggested_fixes": []}

    gc.generate_code_node(st)

    assert calls == {"decision": 1, "regen": 1, "patch": 0}
