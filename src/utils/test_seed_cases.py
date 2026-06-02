"""Deterministic local seed cases used by bootstrap and full test generation."""

from typing import Any, Dict, List


def _is_cyclic_sum_segment_count_problem(problem_desc: str) -> bool:
    text = (problem_desc or "").lower()
    markers = (
        "cyclic sequence",
        "segment",
        "sum of elements in the segment is divisible by k",
        "number of different segments",
        "same set of indices",
        "concatenating m copies",
    )
    return sum(1 for marker in markers if marker in text) >= 4


def _count_cyclic_divisible_segments_bruteforce(n: int, m: int, k: int, a: List[int]) -> int:
    total_positions = n * m
    if total_positions > 256:
        raise ValueError("bruteforce helper is only intended for modest certification inputs")

    b = a * m
    total_sum = sum(b)
    answer = 0
    for start in range(total_positions):
        segment_sum = 0
        for length in range(1, total_positions):
            segment_sum += b[(start + length - 1) % total_positions]
            if segment_sum % k == 0:
                answer += 1
    if total_sum % k == 0:
        answer += 1
    return answer % 1000000007


def build_local_certified_tests(problem_desc: str) -> List[Dict[str, Any]]:
    if not _is_cyclic_sum_segment_count_problem(problem_desc):
        return []

    cases = [
        (1, 3, 2, [1]),
        (1, 4, 3, [1]),
        (2, 1, 5, [0, 1]),
        (3, 2, 5, [1, 1, 1]),
    ]

    certified = []
    for n, m, k, a in cases:
        expected = _count_cyclic_divisible_segments_bruteforce(n, m, k, a)
        certified.append(
            {
                "input": f"{n} {m} {k}\n{' '.join(map(str, a))}\n",
                "output": f"{expected}\n",
                "type": "edge",
                "description": "Local exact cyclic wrap certification case",
            }
        )
    return certified
