from __future__ import annotations


def _norm_exact(text: str) -> str:
    normalized_lines = []
    for line in text.strip().splitlines():
        normalized_lines.append(" ".join(line.split()))
    return "\n".join(normalized_lines)


def evaluate_solution_consensus(*, route: str, cases, verifier=None, verifier_ctx=None):
    cases = [c for c in cases if str(c.get("output", "")).strip()]
    if not cases:
        return {"trusted": False, "reason": "no_outputs"}
    if route == "exact_single_answer":
        normalized = {_norm_exact(c["output"]) for c in cases}
        return {
            "trusted": len(normalized) == 1,
            "reason": "route_consensus" if len(normalized) == 1 else "exact_disagreement",
        }
    if route == "trusted_checker_backed_multi_answer":
        if verifier is None:
            return {"trusted": False, "reason": "missing_verifier"}
        accepted = [
            c
            for c in cases
            if verifier(c["input"], c["output"], c.get("witness"), verifier_ctx or {})
        ]
        return {
            "trusted": len(accepted) == len(cases),
            "reason": "route_consensus" if len(accepted) == len(cases) else "verifier_reject",
        }
    return {"trusted": False, "reason": "unsupported_route"}
