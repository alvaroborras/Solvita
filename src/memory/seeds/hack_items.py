"""Seed items for Hacker Test Input Generation memory."""

from typing import Dict, Any, List

HACK_SEED_ITEMS: List[Dict[str, Any]] = [
    {
        "text": "For array inputs, target the endpoints: arrays with only 1 element, or arrays sorted backwards.",
        "payload": {
            "adversarial_patterns": ["single_element_array", "reversed_array", "all_same_elements"],
            "edge_cases": ["minimum_n", "maximum_n"]
        },
        "tags": ["array", "edge_case"]
    },
    {
        "text": "For graph problems, generate sparse graphs (e.g., a single long line or star graph) and disconnected components if allowed.",
        "payload": {
            "adversarial_patterns": ["line_graph", "star_graph", "disconnected_graph"],
            "edge_cases": ["forest", "isolated_vertices"]
        },
        "tags": ["graph", "tree", "edge_case"]
    },
    {
        "text": "For string problems, test strings with identical characters or alternating two characters to break naive greedy matching.",
        "payload": {
            "adversarial_patterns": ["identical_characters_string", "alternating_characters"],
            "edge_cases": ["empty_string_if_allowed", "single_char"]
        },
        "tags": ["string", "pattern_breaking"]
    },
    {
        "text": "For math/number-theoretic problems, always include tests with primes, 1, 0 (if allowed), and powers of 2.",
        "payload": {
            "adversarial_patterns": ["prime_numbers", "powers_of_two"],
            "edge_cases": ["zero", "one", "maximum_value"]
        },
        "tags": ["math", "number_theory", "edge_case"]
    }
]
