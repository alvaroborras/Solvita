import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.nodes.compile_code import prepare_executable
from src.nodes.phase_transition import phase_transition_node
from src.nodes.routing import hack_outcome_routing


def test_prepare_executable_returns_existing_binary_path_on_windows(tmp_path, monkeypatch):
    def fake_compile_cpp(source_path, exe_path, **kwargs):
        output_path = exe_path
        if sys.platform == "win32" and exe_path.suffix != ".exe":
            output_path = exe_path.with_suffix(".exe")
        output_path.write_text("binary", encoding="utf-8")
        return True, ""

    monkeypatch.setattr("src.nodes.compile_code.compile_cpp", fake_compile_cpp)

    exe_path, errors = prepare_executable(
        "int main() { return 0; }",
        "C++",
        tmp_path,
    )

    assert errors == []
    assert exe_path is not None
    assert exe_path.exists()
    if sys.platform == "win32":
        assert exe_path.suffix == ".exe"


def test_phase_transition_loops_hacker_failures_back_to_codegen():
    result = phase_transition_node(
        {
            "current_phase": "HACKER",
            "hack_passed": False,
            "iteration": 0,
            "hack_round": 2,
            "messages": [{"role": "assistant", "content": "stale"}],
        }
    )

    assert result["current_phase"] == "CODEGEN"
    assert result["iteration"] == 1
    assert result["hack_round"] == 0
    assert result["status"] == "pending"
    assert result["messages"] == []


def test_hack_outcome_routing_marks_terminal_failure_after_iteration_budget():
    route = hack_outcome_routing(
        {
            "hack_passed": False,
            "iteration": 1,
            "max_iterations": 1,
        }
    )

    assert route == "terminal_failure"
