import pytest

from src.heuristic.agents import assert_no_validation_leakage, solver_prompt
from src.heuristic.operators import get_operator


def test_solver_prompt_routes_patch_and_rejects_validation_context():
    prompt = solver_prompt(
        operator=get_operator("tune_parameters"),
        parent_sources=["int main(){}"],
        training_feedback={"weak_cluster": "large"},
        strategies=[],
    )
    assert "minimal constrained patch" in prompt.user
    rewrite = solver_prompt(
        operator=get_operator("new_paradigm"),
        parent_sources=[],
        training_feedback={},
        strategies=[],
    )
    assert "complete bundle rewrite" in rewrite.user
    assert_no_validation_leakage({"training_scores": [1, 2]})
    with pytest.raises(ValueError, match="validation"):
        assert_no_validation_leakage({"validation_outputs": ["secret"]})
