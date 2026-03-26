from src.nodes.plan_solution import build_plan_prompt


def test_build_plan_prompt_truncates_large_context():
    prompt = build_plan_prompt(
        problem_desc="P" * 20000,
        problem_types=["dp", "graph", "math"],
        constraints={"payload": "C" * 10000},
        advice="A" * 6000,
        compact=False,
    )

    assert "[TRUNCATED" in prompt
    assert len(prompt) < 30000
