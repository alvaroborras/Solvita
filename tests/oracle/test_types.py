from src.oracle.types import (
    AcceptedArtifactKind,
    OraclePlan,
    OracleRoute,
    VerifierProvenance,
)


def test_checker_backed_route_requires_bundle_artifact():
    assert OracleRoute.TRUSTED_CHECKER_BACKED_MULTI.value == "trusted_checker_backed_multi"
    assert AcceptedArtifactKind.CHECKER_BUNDLE.value == "checker_bundle"


def test_oracle_plan_exposes_structured_fields():
    plan = OraclePlan(
        trainability_class="exact_single_answer",
        primary_family_id="oracle.dp.topdown",
        fallback_family_id=None,
        route=OracleRoute.EXACT_SINGLE_ANSWER,
        acceptance_mode="safe",
        prompt_payloads=[{"family_id": "oracle.dp.topdown", "text": "Top-down DP"}],
    )
    assert plan.primary_family_id == "oracle.dp.topdown"
    assert plan.route is OracleRoute.EXACT_SINGLE_ANSWER
    assert plan.acceptance_mode == "safe"
    assert plan.prompt_payloads == [{"family_id": "oracle.dp.topdown", "text": "Top-down DP"}]


def test_verifier_provenance_requires_explicit_source():
    provenance = VerifierProvenance(
        kind="official_checker",
        source_id="dataset://checker/abc",
        schema_version="v1",
    )
    assert provenance.kind == "official_checker"
    assert provenance.source_id.startswith("dataset://")
    assert provenance.schema_version == "v1"
