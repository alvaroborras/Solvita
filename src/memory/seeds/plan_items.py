"""Seed memory items for plan namespace."""

PLAN_SEED_ITEMS = [
    {
        "text": "Dynamic programming problem: identify optimal substructure and overlapping subproblems",
        "tags": ["dp", "optimization"],
        "payload": {
            "problem_tags": ["dp", "memoization"],
            "subfunctions": ["define_dp_state", "identify_transitions", "handle_base_cases"],
            "canonical_hints": "Look for optimal substructure; check if subproblems overlap; consider top-down vs bottom-up",
        },
    },
    {
        "text": "Graph traversal: choose BFS for shortest path, DFS for connectivity/cycles",
        "tags": ["graph", "traversal"],
        "payload": {
            "problem_tags": ["graph", "bfs", "dfs"],
            "subfunctions": ["build_adjacency_list", "track_visited", "implement_queue_or_stack"],
            "canonical_hints": "BFS for unweighted shortest path; DFS for cycle detection or topological sort",
        },
    },
    {
        "text": "Greedy algorithm: verify greedy choice property and optimal substructure",
        "tags": ["greedy", "optimization"],
        "payload": {
            "problem_tags": ["greedy"],
            "subfunctions": ["sort_by_criterion", "make_local_optimal_choice", "prove_correctness"],
            "canonical_hints": "Greedy works if local optimal leads to global optimal; often involves sorting",
        },
    },
    {
        "text": "Two pointers technique for array/string problems with linear constraints",
        "tags": ["two_pointers", "array"],
        "payload": {
            "problem_tags": ["two_pointers", "sliding_window"],
            "subfunctions": ["initialize_pointers", "maintain_invariant", "move_pointers_conditionally"],
            "canonical_hints": "Use when searching pairs or subarrays; maintain invariant between pointers",
        },
    },
    {
        "text": "Binary search for monotonic search space or optimization problems",
        "tags": ["binary_search", "search"],
        "payload": {
            "problem_tags": ["binary_search"],
            "subfunctions": ["define_search_space", "implement_predicate", "handle_boundaries"],
            "canonical_hints": "Check if answer space is monotonic; binary search on answer if predicate is monotonic",
        },
    },
    {
        "text": "Prefix sums for range query problems with static arrays",
        "tags": ["prefix_sum", "array"],
        "payload": {
            "problem_tags": ["prefix_sum", "range_query"],
            "subfunctions": ["build_prefix_array", "query_range_in_O1"],
            "canonical_hints": "Precompute cumulative sums for O(1) range queries",
        },
    },
    {
        "text": "Segment tree or Fenwick tree for dynamic range queries with updates",
        "tags": ["segment_tree", "fenwick_tree"],
        "payload": {
            "problem_tags": ["range_query", "updates"],
            "subfunctions": ["build_tree", "query_range", "update_point"],
            "canonical_hints": "Use when both queries and updates are needed; Fenwick for sum/xor, segment tree for general",
        },
    },
    {
        "text": "Union-Find (Disjoint Set Union) for connectivity and grouping problems",
        "tags": ["union_find", "dsu"],
        "payload": {
            "problem_tags": ["union_find", "connectivity"],
            "subfunctions": ["initialize_parent", "find_with_path_compression", "union_by_rank"],
            "canonical_hints": "Efficient for dynamic connectivity; use path compression and union by rank",
        },
    },
    {
        "text": "Backtracking for combinatorial search and constraint satisfaction",
        "tags": ["backtracking", "search"],
        "payload": {
            "problem_tags": ["backtracking", "permutations", "combinations"],
            "subfunctions": ["define_state", "explore_choices", "prune_invalid_branches"],
            "canonical_hints": "Explore all possibilities with pruning; restore state after each choice",
        },
    },
    {
        "text": "Bit manipulation for problems involving subsets, masks, or XOR properties",
        "tags": ["bit_manipulation", "bitmask"],
        "payload": {
            "problem_tags": ["bit_manipulation", "bitmask_dp"],
            "subfunctions": ["iterate_subsets", "check_set_bits", "xor_properties"],
            "canonical_hints": "Use bitmasks for subset enumeration; XOR has useful properties (self-inverse, associative)",
        },
    },
]
