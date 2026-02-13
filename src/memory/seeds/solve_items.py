"""Seed memory items for solve namespace."""

SOLVE_SEED_ITEMS = [
    {
        "text": "Implement careful index bounds checking to avoid off-by-one errors",
        "tags": ["debugging", "bounds"],
        "payload": {
            "step_strategies": [
                "Check loop bounds: use <= vs < carefully",
                "Verify array access indices are within [0, n-1]",
                "Test edge cases: empty array, single element, all same values",
            ],
            "skills": [],
            "anti_patterns": [
                "Forgetting to check i < n before accessing a[i]",
                "Mixing 0-indexed and 1-indexed logic",
            ],
        },
    },
    {
        "text": "Use appropriate data types to avoid integer overflow",
        "tags": ["overflow", "data_types"],
        "payload": {
            "step_strategies": [
                "Use long long for intermediate calculations if result can exceed 2^31",
                "Consider modulo arithmetic if problem specifies MOD",
                "Check if multiplication can overflow before computing",
            ],
            "skills": [],
            "anti_patterns": [
                "Using int when sum of n elements can exceed INT_MAX",
                "Forgetting to cast to long long before multiplication",
            ],
        },
    },
    {
        "text": "Optimize I/O for large inputs using fast I/O techniques",
        "tags": ["io", "performance"],
        "payload": {
            "step_strategies": [
                "Use ios_base::sync_with_stdio(false) and cin.tie(nullptr)",
                "Avoid endl; use '\\n' instead",
                "Consider reading all input at once for very large datasets",
            ],
            "skills": [],
            "anti_patterns": [
                "Using endl in tight loops (flushes buffer)",
                "Mixing cin/cout with scanf/printf after disabling sync",
            ],
        },
    },
    {
        "text": "Implement sorting with custom comparators when needed",
        "tags": ["sorting", "comparator"],
        "payload": {
            "step_strategies": [
                "Define comparator as lambda or struct for clarity",
                "Ensure comparator defines strict weak ordering",
                "Test comparator with equal elements",
            ],
            "skills": [{"skill_id": "quick_sort", "path": "skills/quick_sort.md"}],
            "anti_patterns": [
                "Comparator that returns true for equal elements (violates strict weak ordering)",
                "Not handling tie-breaking in multi-key sorting",
            ],
        },
    },
    {
        "text": "Handle special cases and edge conditions explicitly",
        "tags": ["edge_cases", "robustness"],
        "payload": {
            "step_strategies": [
                "Check n=0, n=1 separately if algorithm assumes n>=2",
                "Handle all-same-value arrays",
                "Test with minimum and maximum constraint values",
            ],
            "skills": [],
            "anti_patterns": [
                "Assuming array has at least 2 elements without checking",
                "Not testing with constraint boundaries",
            ],
        },
    },
    {
        "text": "Use memoization or tabulation to avoid redundant computation in DP",
        "tags": ["dp", "optimization"],
        "payload": {
            "step_strategies": [
                "Initialize DP table with sentinel values",
                "Check if state already computed before recursing",
                "Consider space optimization if only recent states are needed",
            ],
            "skills": [],
            "anti_patterns": [
                "Forgetting to memoize recursive calls",
                "Using uninitialized DP table entries",
            ],
        },
    },
    {
        "text": "Implement graph algorithms with correct visited tracking",
        "tags": ["graph", "visited"],
        "payload": {
            "step_strategies": [
                "Use boolean array or set for visited nodes",
                "Mark visited at the right time (when enqueued for BFS, when entered for DFS)",
                "Reset visited array between independent queries if needed",
            ],
            "skills": [],
            "anti_patterns": [
                "Marking visited after dequeue in BFS (can cause duplicates)",
                "Forgetting to reset visited for multiple test cases",
            ],
        },
    },
    {
        "text": "Debug with small manual test cases before submitting",
        "tags": ["debugging", "testing"],
        "payload": {
            "step_strategies": [
                "Trace algorithm by hand on small input (n=3 or n=4)",
                "Check output format matches expected (spaces, newlines)",
                "Verify algorithm handles provided examples correctly",
            ],
            "skills": [],
            "anti_patterns": [
                "Submitting without testing on provided examples",
                "Not checking output format requirements",
            ],
        },
    },
]
