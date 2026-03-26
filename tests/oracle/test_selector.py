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
    assert plan.primary_family_id.startswith("oracle.")
    assert plan.acceptance_mode == "safe"
    assert plan.prompt_payloads


def test_route_b_accepts_checker_bundle_not_expected_output():
    artifact = build_accepted_artifact(
        route=OracleRoute.TRUSTED_CHECKER_BACKED_MULTI,
        input_text="1\n",
        output_text="2 1\n",
        verifier_provenance={"kind": "official_checker", "source_id": "dataset://checker/demo"},
        evidence={"route": "trusted_checker_backed_multi"},
    )
    assert artifact["kind"] == AcceptedArtifactKind.CHECKER_BUNDLE.value
