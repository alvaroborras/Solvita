from src.oracle.truth import evaluate_solution_consensus


def test_exact_route_disagreement_uses_normalized_output():
    result = evaluate_solution_consensus(
        route="exact_single_answer",
        cases=[
            {"input": "1\n", "output": "1 2\n", "witness": None},
            {"input": "1\n", "output": "1  2\n", "witness": None},
        ],
        verifier=None,
    )
    assert result["trusted"] is True


def test_checker_route_text_disagreement_does_not_imply_failure():
    def fake_verifier(input_text, output_text, witness, verifier_ctx):
        assert input_text == "3\n"
        assert witness is None
        assert verifier_ctx["kind"] == "official_checker"
        return output_text in {"1 2\n", "2 1\n"}

    result = evaluate_solution_consensus(
        route="trusted_checker_backed_multi_answer",
        cases=[
            {"input": "3\n", "output": "1 2\n", "witness": None},
            {"input": "3\n", "output": "2 1\n", "witness": None},
        ],
        verifier=fake_verifier,
        verifier_ctx={"kind": "official_checker"},
    )
    assert result["trusted"] is True
    assert result["reason"] == "route_consensus"
