def classify_trainability(
    *,
    has_checker: bool,
    is_interactive: bool,
    is_multi_answer: bool,
    has_trusted_checker: bool = False,
    has_trusted_normalizer: bool = False,
) -> str:
    if is_interactive:
        return "unsupported"
    if is_multi_answer:
        if has_checker and has_trusted_checker:
            return "trusted_checker_backed_multi_answer"
        return "unsupported"
    return "exact_single_answer"
