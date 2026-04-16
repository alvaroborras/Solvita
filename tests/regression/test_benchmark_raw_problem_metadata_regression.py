from scripts.run_benchmark import _build_raw_problem


def test_build_raw_problem_includes_problem_identity_metadata():
    raw_problem = _build_raw_problem(
        "code-contest",
        {
            "name": "1575_A. Another Sorting Problem",
            "question_id": "1575_A",
        },
        public_tests=[],
        problem_id="codecontests_1575_A__Another_Sorting_Problem",
    )

    metadata = raw_problem["_metadata"]
    assert metadata["problem_id"] == "codecontests_1575_A__Another_Sorting_Problem"
    assert metadata["name"] == "1575_A. Another Sorting Problem"
    assert metadata["question_id"] == "1575_A"
