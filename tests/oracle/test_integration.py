from src.oracle.types import OraclePlan, OracleRoute
from src.nodes.generate_tests import _resolve_oracle_selection


def test_online_oracle_path_consumes_oracle_plan(monkeypatch):
    captured = {}

    def fake_build_plan(**kwargs):
        captured["kwargs"] = kwargs
        return OraclePlan(
            trainability_class="exact_single_answer",
            primary_family_id="oracle.dp.topdown",
            fallback_family_id=None,
            route=OracleRoute.EXACT_SINGLE_ANSWER,
            acceptance_mode="safe",
            prompt_payloads=[{"family_id": "oracle.dp.topdown", "text": "Top-down DP"}],
        )

    monkeypatch.setattr("src.nodes.generate_tests.build_rule_based_oracle_plan", fake_build_plan)
    state = {
        "raw_problem": {"description": "demo", "tags": ["dp"]},
        "config": {"trainable_memory": {"enabled": False}},
    }
    plan, advice, item_ids, provenance = _resolve_oracle_selection(
        state=state,
        config=state["config"],
        problem_desc="demo",
        constraints={"n": "1e5"},
        canonical={"tags": ["dp"]},
        checker_exe=None,
    )
    assert captured["kwargs"]["trainability_class"] == "exact_single_answer"
    assert plan.primary_family_id == "oracle.dp.topdown"
    assert "oracle.dp.topdown" in advice
    assert item_ids == []
    assert provenance is None
