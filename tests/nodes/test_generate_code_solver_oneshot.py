import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


class _FakeMem:
    def get_injection(self, **kwargs):
        return "", []


def test_initial_codegen_marks_solver_oneshot_spent(monkeypatch):
    from src.graph.state import create_initial_state
    from src.nodes import generate_code as gc

    monkeypatch.setattr(gc, "build_solver_network_block", lambda s, c: "## graph block")
    monkeypatch.setattr(gc, "_generate_with_compact_retry", lambda *a, **k: "int main(){return 0;}")
    monkeypatch.setattr(gc, "_self_validate", lambda *a, **k: (True, [], 0))
    monkeypatch.setattr(gc, "sanitize_cpp", lambda x: x)
    monkeypatch.setattr(gc, "MemoryClient", lambda **kw: _FakeMem())

    st = create_initial_state(
        {"description": "d", "public_tests": []},
        {"max_iterations": 5, "solver_network": {"enabled": True, "graph_dir": "/tmp"}},
    )
    st["problem"]["canonical"] = {"objective": "o"}
    st["plan"]["algorithm_choice"] = "a"
    st["plan"]["implementation_steps"] = ["s"]

    out = gc.generate_code_node(st)
    assert out.get("solver_network_oneshot_spent") is True


def test_patch_codegen_does_not_mark_solver_oneshot(monkeypatch):
    from src.graph.state import create_initial_state
    from src.nodes import generate_code as gc

    calls = {"n": 0}

    def _track(*a, **k):
        calls["n"] += 1
        return ""

    monkeypatch.setattr(gc, "build_solver_network_block", _track)
    monkeypatch.setattr(gc, "_generate_with_compact_retry", lambda *a, **k: "int main(){return 0;}")
    monkeypatch.setattr(gc, "_self_validate", lambda *a, **k: (True, [], 0))
    monkeypatch.setattr(gc, "sanitize_cpp", lambda x: x)
    monkeypatch.setattr(gc, "MemoryClient", lambda **kw: _FakeMem())

    st = create_initial_state(
        {"description": "d", "public_tests": []},
        {"max_iterations": 5, "solver_network": {"enabled": True, "graph_dir": "/tmp"}},
    )
    st["problem"]["canonical"] = {"objective": "o"}
    st["plan"]["algorithm_choice"] = "a"
    st["plan"]["implementation_steps"] = ["s"]
    st["solution"]["code"] = "int main(){return 0;}"
    st["iteration"] = 1

    out = gc.generate_code_node(st)
    assert out.get("solver_network_oneshot_spent") is None
    assert calls["n"] == 0
