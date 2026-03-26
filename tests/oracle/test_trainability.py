from src.oracle.trainability import classify_trainability


def test_exact_single_answer_problem_is_supported():
    result = classify_trainability(
        has_checker=False,
        is_interactive=False,
        is_multi_answer=False,
        has_trusted_normalizer=False,
    )
    assert result == "exact_single_answer"


def test_checker_backed_multi_answer_requires_trusted_checker():
    result = classify_trainability(
        has_checker=True,
        is_interactive=False,
        is_multi_answer=True,
        has_trusted_checker=True,
        has_trusted_normalizer=False,
    )
    assert result == "trusted_checker_backed_multi_answer"


def test_simple_normalizable_multi_answer_is_deferred_in_v1():
    result = classify_trainability(
        has_checker=False,
        is_interactive=False,
        is_multi_answer=True,
        has_trusted_checker=False,
        has_trusted_normalizer=True,
    )
    assert result == "unsupported"
