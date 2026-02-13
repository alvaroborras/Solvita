"""Seed memory items for test namespace."""

TEST_SEED_ITEMS = [
    {
        "text": "Generate test cases covering constraint boundaries (min/max values)",
        "tags": ["boundary", "constraints"],
        "payload": {
            "constraints_patterns": ["n=1", "n=max_n", "all values = 0", "all values = max_val"],
            "generation_strategies": [
                "Include test with minimum n",
                "Include test with maximum n",
                "Include test with all elements at boundary values",
            ],
            "validator_pitfalls": [
                "Forgetting to check n >= min_n",
                "Not validating that values are within [min_val, max_val]",
            ],
        },
    },
    {
        "text": "Generate random tests with uniform distribution across constraint range",
        "tags": ["random", "distribution"],
        "payload": {
            "constraints_patterns": ["n in [1, max_n]", "values in [min_val, max_val]"],
            "generation_strategies": [
                "Use RNG with proper seeding",
                "Generate n uniformly in valid range",
                "Generate each element uniformly in valid range",
            ],
            "validator_pitfalls": [
                "Using uninitialized RNG (non-deterministic)",
                "Not checking that generated values satisfy constraints",
            ],
        },
    },
    {
        "text": "Include corner cases: empty input, single element, all identical elements",
        "tags": ["corner_cases", "edge"],
        "payload": {
            "constraints_patterns": ["n=0 (if allowed)", "n=1", "all a[i] equal"],
            "generation_strategies": [
                "Generate test with n=1",
                "Generate test where all elements are the same",
                "Generate test with alternating pattern if relevant",
            ],
            "validator_pitfalls": [
                "Rejecting valid single-element input",
                "Not handling all-same-value case",
            ],
        },
    },
    {
        "text": "For graph problems, generate connected and disconnected graphs",
        "tags": ["graph", "connectivity"],
        "payload": {
            "constraints_patterns": ["m edges", "n nodes", "connected vs disconnected"],
            "generation_strategies": [
                "Generate spanning tree first to ensure connectivity",
                "Add random edges up to m",
                "Generate disconnected graph by creating separate components",
            ],
            "validator_pitfalls": [
                "Not checking that edges are within [1, n]",
                "Allowing self-loops or multi-edges if not permitted",
            ],
        },
    },
    {
        "text": "For string problems, include strings with special characters and edge lengths",
        "tags": ["string", "characters"],
        "payload": {
            "constraints_patterns": ["length in [1, max_len]", "allowed character set"],
            "generation_strategies": [
                "Generate string of length 1",
                "Generate string of maximum length",
                "Include strings with only one unique character",
            ],
            "validator_pitfalls": [
                "Not checking string length",
                "Allowing characters outside permitted set",
            ],
        },
    },
    {
        "text": "Validate input format strictly: correct number of tokens, valid separators",
        "tags": ["validation", "format"],
        "payload": {
            "constraints_patterns": ["expected number of lines", "expected tokens per line"],
            "generation_strategies": [
                "Count tokens and validate against expected format",
                "Check for extra whitespace or missing newlines",
            ],
            "validator_pitfalls": [
                "Not checking for trailing whitespace",
                "Accepting input with wrong number of elements",
            ],
        },
    },
    {
        "text": "Use checker to verify output correctness for problems with multiple valid answers",
        "tags": ["checker", "validation"],
        "payload": {
            "constraints_patterns": ["multiple valid outputs", "output must satisfy property"],
            "generation_strategies": [
                "Implement checker that validates output properties",
                "Do not compare output string directly if multiple answers exist",
            ],
            "validator_pitfalls": [
                "Using string comparison when multiple answers are valid",
                "Not checking that output satisfies problem constraints",
            ],
        },
    },
    {
        "text": "Generate large tests to stress-test performance and catch TLE",
        "tags": ["performance", "stress"],
        "payload": {
            "constraints_patterns": ["n = max_n", "worst-case complexity"],
            "generation_strategies": [
                "Generate test with maximum n",
                "Generate worst-case input for expected algorithm (e.g., sorted array for quicksort)",
            ],
            "validator_pitfalls": [
                "Not testing with maximum constraints",
                "Generator or validator timing out on large input",
            ],
        },
    },
]
