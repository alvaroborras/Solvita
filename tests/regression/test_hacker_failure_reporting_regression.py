import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.nodes.hack_test import hack_test_node


def test_hack_test_surfaces_structured_generation_failure(monkeypatch):
    monkeypatch.setattr("src.nodes.hack_test.Path.exists", lambda self: True)
    class DummyLLM:
        @staticmethod
        def build_role_config(config, role):
            return config

        def __init__(self, *args, **kwargs):
            pass

    monkeypatch.setattr("src.nodes.hack_test.UnifiedLLMClient", DummyLLM)

    class DummyMemory:
        def get_injection(self, *args, **kwargs):
            return "", []

    monkeypatch.setattr("src.nodes.hack_test.MemoryClient", lambda **kw: DummyMemory())
    monkeypatch.setattr(
        "src.nodes.hack_test.run_code_analyst",
        lambda *a, **k: (
            {
                "bug_class": "unknown",
                "confidence": "low",
                "evidence": [],
                "suggested_route": "semantic",
                "input_hypothesis": [],
            },
            [],
        ),
    )
    monkeypatch.setattr(
        "src.nodes.hack_test.cascading_execution_router",
        lambda *a, **k: (
            "failed",
            "",
            [
                'ROUTER_META: {"failure_kind": "validator_rejected", "failure_reason": "Strings must be pairwise distinct"}',
                "Router: CRITICAL. Stress generator fallback also failed: Validation Failed: duplicate",
            ],
            [],
        ),
    )

    state = {
        "problem": {"description": "desc", "canonical": {}},
        "solution": {"code": "int main() {}", "executable_path": "/tmp/sol.exe"},
        "config": {},
        "tests": {},
        "hack_round": 0,
    }

    result = hack_test_node(state)

    assert result["hack_result"] == "GEN_FAILED"
    assert result["generator_failure_kind"] == "validator_rejected"
    assert "pairwise distinct" in result["generator_failure_reason"]
