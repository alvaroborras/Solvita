from src.oracle.evidence import build_accepted_artifact
from src.oracle.selector import build_rule_based_oracle_plan
from src.oracle.types import AcceptedArtifactKind, OracleRoute


def test_selector_returns_structured_oracle_plan():
    plan = build_rule_based_oracle_plan(
        trainability_class="exact_single_answer",
        problem_tags=["dp"],
        problem_constraints={"n": "1e5"},
        acceptance_mode="safe",
    )
    assert plan.primary_family_id == "oracle.dp.topdown"
    assert plan.fallback_family_id == "oracle.enumeration.n_nested_loops"
    assert plan.acceptance_mode == "safe"
    assert [payload["family_id"] for payload in plan.prompt_payloads] == [
        "oracle.dp.topdown",
        "oracle.enumeration.n_nested_loops",
    ]


def test_selector_uses_enumeration_primary_for_non_dp_tags():
    plan = build_rule_based_oracle_plan(
        trainability_class="exact_single_answer",
        problem_tags=["math"],
        problem_constraints={"n": "1e5"},
        acceptance_mode="safe",
    )
    assert plan.primary_family_id == "oracle.enumeration.n_nested_loops"
    assert plan.fallback_family_id == "oracle.dp.topdown"
    assert [payload["family_id"] for payload in plan.prompt_payloads] == [
        "oracle.enumeration.n_nested_loops",
        "oracle.dp.topdown",
    ]


def test_route_b_accepts_checker_bundle_not_expected_output():
    artifact = build_accepted_artifact(
        route=OracleRoute.TRUSTED_CHECKER_BACKED_MULTI,
        input_text="1\n",
        output_text="2 1\n",
        verifier_provenance={"kind": "official_checker", "source_id": "dataset://checker/demo"},
        evidence={"route": "trusted_checker_backed_multi"},
    )
    assert artifact["kind"] == AcceptedArtifactKind.CHECKER_BUNDLE.value
