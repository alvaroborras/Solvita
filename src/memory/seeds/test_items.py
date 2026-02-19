"""Seed memory items for test namespace.

Covers 8 base categories + 7 advanced algorithm-specific categories
based on competitive programming best practices and adversarial test design.

Categories:
 1. Boundary / Constraint         (items 1-2)
 2. Structural Extremes           (items 3-5, incl. Interval DP LCS worst case)
 3. Graph Structures              (items 6-8, incl. SPFA hack + unordered_map)
 4. Tree Structures               (item 9, incl. stack overflow warning)
 5. Arithmetic / Overflow         (items 10-11)
 6. String                        (items 12-13, incl. Fibonacci KMP stress)
 7. Performance / Stress          (items 14-15, incl. Dinic layered graph)
 8. Checker / Multi-solution      (items 16-18, incl. DAG topological checker)
 9. Interval DP                   (item 19)
10. Anti-Hash                     (item 20)
11. Trie Structures               (item 21)
12. Number Theory                 (item 22)
13. Computational Geometry        (item 23)
14. Multi-Test Engineering        (item 24)
15. Adaptive Interaction          (item 25)
16. Validator Meta-Testing        (item 26)
17. Data Structure Worst Case     (item 27)
"""

TEST_SEED_ITEMS = [
    # ── Category 1: Boundary / Constraint ──────────────────────────────────
    {
        "text": "Generate test cases covering constraint boundaries (min/max values)",
        "tags": ["boundary", "constraints"],
        "payload": {
            "constraints_patterns": ["n=1", "n=max_n", "all values = 0", "all values = max_val"],
            "generation_strategies": [
                "Include test with minimum n",
                "Include test with maximum n",
                "Include test with all elements at boundary values",
                "Include test with a[i] = 0 alongside max values to test zero-handling branches",
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
                "Use rnd.next() with proper seeding via registerGen",
                "Generate n uniformly in valid range",
                "Generate each element uniformly in valid range",
            ],
            "validator_pitfalls": [
                "Using uninitialized RNG (non-deterministic) — always use testlib rnd",
                "Not checking that generated values satisfy constraints",
            ],
        },
    },

    # ── Category 2: Structural Extremes ────────────────────────────────────
    {
        "text": "Include corner cases: single element, all identical elements, all distinct elements",
        "tags": ["corner_cases", "edge"],
        "payload": {
            "constraints_patterns": ["n=1", "all a[i] equal", "all a[i] distinct"],
            "generation_strategies": [
                "Generate test with n=1",
                "Generate test where all elements are the same",
                "Generate test where all elements are distinct (permutation)",
                "Generate test with alternating pattern if relevant",
            ],
            "validator_pitfalls": [
                "Rejecting valid single-element input",
                "Not handling all-same-value case",
            ],
        },
    },
    {
        "text": "Generate sorted, reverse-sorted, and near-sorted arrays; also serves as LCS/interval-DP worst case",
        "tags": ["sorted", "structural", "stress", "interval-dp"],
        "payload": {
            "constraints_patterns": [
                "array sorted ascending", "array sorted descending",
                "almost sorted", "two completely different alphabets (LCS O(N^2) worst)",
            ],
            "generation_strategies": [
                "Generate strictly increasing sequence: a[i] = i+1",
                "Generate strictly decreasing sequence: a[i] = n-i",
                "Generate nearly sorted: sorted array with k random swaps (k=1..5)",
                "Generate sawtooth: alternating small/large values",
                "For LCS worst case: generate A = 'aaa...a' (n zeros), B = 'bbb...b' (n ones) — zero matches force full DP table traversal",
                "For palindrome/interval-DP: generate string with no repeated chars to maximize state count",
            ],
            "validator_pitfalls": [
                "Not verifying that sorted arrays stay within value constraints",
                "For LCS/palindrome problems: not checking both strings have correct length",
            ],
        },
    },
    {
        "text": "Generate permutations: identity, reversed, and random shuffles",
        "tags": ["permutation", "structural"],
        "payload": {
            "constraints_patterns": ["permutation of [1..n]", "all values distinct", "values in [1, n]"],
            "generation_strategies": [
                "Generate identity permutation: a[i] = i",
                "Generate reversed permutation: a[i] = n+1-i",
                "Use rnd.shuffle() for random permutation",
                "Generate cyclic shift: a[i] = (i % n) + 1",
            ],
            "validator_pitfalls": [
                "Not verifying all values in [1, n] are present exactly once",
                "Allowing duplicate values in a permutation",
            ],
        },
    },

    # ── Category 3: Graph Structures ───────────────────────────────────────
    {
        "text": "For graph problems, generate connected and disconnected graphs",
        "tags": ["graph", "connectivity"],
        "payload": {
            "constraints_patterns": ["m edges", "n nodes", "connected vs disconnected"],
            "generation_strategies": [
                "Generate spanning tree first to ensure connectivity, then add random edges",
                "Generate disconnected graph by creating separate components",
                "Ensure no self-loops and no multi-edges unless explicitly allowed",
            ],
            "validator_pitfalls": [
                "Not checking that edges are within [1, n]",
                "Allowing self-loops or multi-edges if not permitted",
            ],
        },
    },
    {
        "text": "Generate special graph topologies: chain, star, complete graph, bipartite; also SPFA adversarial grid",
        "tags": ["graph", "topology", "special", "adversarial", "shortest-path"],
        "payload": {
            "constraints_patterns": [
                "chain: n-1 edges", "star: degree-n-1 center",
                "complete: n*(n-1)/2 edges", "grid graph with back edges for SPFA hack",
            ],
            "generation_strategies": [
                "Chain/path graph: edge i-(i+1) for i in [1, n-1]",
                "Star graph: center=1, edges 1-i for i in [2, n]",
                "Complete graph: all pairs (i, j) for i < j (only for small n ≤ 500)",
                "Bipartite: partition vertices into two sets A, B; edges only between sets",
                "SPFA hack: construct a vertical chain with cheap downward edges and expensive horizontal cross-edges; add selective back-edges to force repeated node relaxation",
                "SPFA hack detail: each node re-enters queue O(n) times, degrading to O(VE) worst case",
            ],
            "validator_pitfalls": [
                "Complete graph on large n exceeds edge limit — guard with n*(n-1)/2 <= max_m",
                "SPFA hack graphs often contain negative edges — validate absence of negative cycles unless problem allows",
            ],
        },
    },
    {
        "text": "Generate DAGs and directed graphs; include adversarial unordered_map hash collision inputs",
        "tags": ["graph", "DAG", "directed", "stl", "hashing", "collision"],
        "payload": {
            "constraints_patterns": [
                "directed edges u->v with u < v for DAG",
                "integer keys that are multiples of GCC hashtable primes",
            ],
            "generation_strategies": [
                "DAG: assign topological order, add edges only from lower to higher index",
                "Random DAG: for each pair (u, v) with u < v, add edge with probability p",
                "Ensure DAG is connected (weakly) by adding chain edges first",
                "unordered_map collision: GCC uses internal primes (126271, 107897...) as bucket counts; generate keys that are all multiples of one such prime so every key lands in bucket 0, degrading insertion to O(n) per operation",
                "Concretely: output n, then 1*107897, 2*107897, ..., n*107897 as the key sequence",
            ],
            "validator_pitfalls": [
                "Back edges violate DAG property — validate with topological sort",
                "Hash collision inputs are Valid but Malicious — standard range checks cannot detect them; document this as an intentional adversarial seed",
            ],
        },
    },

    # ── Category 4: Tree Structures ────────────────────────────────────────
    {
        "text": "Generate special tree structures: bamboo (chain), star, caterpillar, random tree, complete binary",
        "tags": ["tree", "special", "stack-overflow"],
        "payload": {
            "constraints_patterns": ["n nodes", "n-1 edges", "connected acyclic"],
            "generation_strategies": [
                "Bamboo/chain tree: parent[i] = i-1 for i in [2, n] — triggers stack overflow in recursive DFS",
                "Star tree: parent[i] = 1 for all i in [2, n] — maximizes degree-1 aggregation in tree DP",
                "Random tree: rnd.wnext(i-1, t) for positive t gives chain-biased, negative t gives star-biased trees",
                "Caterpillar: build main chain of length n/2, then attach remaining nodes to random positions on chain — mixes deep recursion with high-degree aggregation",
                "Complete binary tree: parent[i] = i//2",
                "For tree DP: bamboo tests information propagation distance; star tests single-node aggregation cost",
                "After generating parent array, shuffle node labels via rnd.perm(n) to hide topology from solvers",
            ],
            "validator_pitfalls": [
                "Tree must have exactly n-1 edges and be connected — verify both with DSU or BFS",
                "Parent array must not create cycles: in Prufer-free construction ensure parent[i] < i before shuffle",
                "Check that shuffled edge list still forms a valid tree after relabeling",
            ],
        },
    },

    # ── Category 5: Arithmetic / Overflow ──────────────────────────────────
    {
        "text": "Generate arithmetic overflow stress tests: values near INT64 boundaries",
        "tags": ["overflow", "arithmetic", "numeric"],
        "payload": {
            "constraints_patterns": ["values up to 1e18", "products may exceed int64", "a*b overflow risk"],
            "generation_strategies": [
                "Include test with a[i] = 10^18 (maximum int64-safe value)",
                "Include test with a[i] = -10^18 for signed problems",
                "Generate pairs (a, b) where a*b would overflow int64 — tests __int128 usage",
                "For interval DP (e.g. matrix chain): alternate dim[i] between 1000 and 1 — maximizes intermediate products; final cost may exceed int64 if unchecked",
                "Generate a[i] = 0 alongside max values to test zero-handling branches",
            ],
            "validator_pitfalls": [
                "Not validating that values fit in long long (int64)",
                "Allowing values that cause intermediate overflow in the validator itself",
                "For interval DP: independently compute minimum cost and assert it fits in long long before accepting the test",
            ],
        },
    },
    {
        "text": "Generate tests with negative numbers, zeros, and mixed-sign arrays",
        "tags": ["negative", "numeric", "mixed"],
        "payload": {
            "constraints_patterns": ["values in [-max_val, max_val]", "can be zero", "mixed positive/negative"],
            "generation_strategies": [
                "Generate all-negative array: a[i] = -rnd.next(1, max_val)",
                "Generate array with exactly one zero and rest positive",
                "Generate alternating positive/negative",
                "Generate array summing to zero (cancellation test)",
            ],
            "validator_pitfalls": [
                "Not allowing negative values when problem permits them",
                "Assuming all values are positive without checking constraints",
            ],
        },
    },

    # ── Category 6: String ─────────────────────────────────────────────────
    {
        "text": "For string problems, include strings with special characters and edge lengths",
        "tags": ["string", "characters"],
        "payload": {
            "constraints_patterns": ["length in [1, max_len]", "allowed character set"],
            "generation_strategies": [
                "Generate string of length 1",
                "Generate string of maximum length",
                "Include strings with only one unique character (e.g., 'aaa...a')",
                "Include strings using only first and last characters of the allowed set",
                "Include strings where every character appears exactly once",
            ],
            "validator_pitfalls": [
                "Not checking string length bounds",
                "Allowing characters outside permitted character set",
            ],
        },
    },
    {
        "text": "Generate palindromes, periodic strings, and Fibonacci strings to stress KMP/Z-algorithm/suffix array",
        "tags": ["string", "palindrome", "periodic", "kmp", "stress"],
        "payload": {
            "constraints_patterns": ["string of length n", "characters from given alphabet"],
            "generation_strategies": [
                "Palindrome: generate first half randomly, mirror to second half",
                "Periodic string: repeat base pattern of length k, period divides n",
                "All-same: s = 'a' * n",
                "Fibonacci string: S0='a', S1='b', S_i = S_{i-1} + S_{i-2}; contains maximum number of distinct border lengths, maximizes KMP fail-pointer back-jumps and Z-algorithm comparisons",
                "Almost-palindrome: palindrome with one character changed at center",
                "Anti-period: string 'aaa...aab' (pattern length n, last char different) forces KMP to traverse all fail pointers before mismatch",
            ],
            "validator_pitfalls": [
                "Palindrome construction must handle odd-length strings correctly",
                "Fibonacci string grows exponentially — generate up to n characters then truncate; validator must check exact length",
                "Not verifying that periodic string length is exactly n",
            ],
        },
    },

    # ── Category 7: Performance / Stress ─────────────────────────────────
    {
        "text": "Validate input format strictly: correct number of tokens, valid separators",
        "tags": ["validation", "format"],
        "payload": {
            "constraints_patterns": ["expected number of lines", "expected tokens per line"],
            "generation_strategies": [
                "Count tokens and validate against expected format",
                "Check for extra whitespace or missing newlines",
                "Use inf.readEoln() and inf.readEof() in testlib validator",
            ],
            "validator_pitfalls": [
                "Not checking for trailing whitespace",
                "Accepting input with wrong number of elements",
                "Forgetting inf.readEof() at end of validator",
            ],
        },
    },
    {
        "text": "Generate large worst-case tests including Dinic layered graph and segment tree cross-midpoint queries",
        "tags": ["performance", "stress", "flow", "adversarial"],
        "payload": {
            "constraints_patterns": ["n = max_n", "worst-case complexity", "layered graph for flow"],
            "generation_strategies": [
                "Generate test with maximum n",
                "Generate worst-case for expected algorithm: sorted array for naive sort, chain graph for DFS",
                "For DP problems: maximize depth of recursion / state space",
                "Dinic layered graph: construct K layers each of size L (K*L ~ n); every node in layer i connects to every node in layer i+1 with capacity 1; this forces O(K) blocking flow rounds each scanning O(K*L^2) edges, approaching O(V^2 E) worst case",
                "Segment tree cross-midpoint queries: generate queries [l, r] such that l is near the right end of the left subtree and r is near the left end of the right subtree, forcing maximum recursion branching at every level",
                "Dense graph (m ≈ max_m) for graph problems",
            ],
            "validator_pitfalls": [
                "Not testing with maximum constraints",
                "Generator or validator timing out on large input (keep generator O(n))",
                "Dinic layered graph: ensure source/sink are distinct and no self-loops",
            ],
        },
    },

    # ── Category 8: Checker / Multi-solution ──────────────────────────────
    {
        "text": "Use checker to verify output correctness for problems with multiple valid answers including DAG topological order",
        "tags": ["checker", "multi-solution", "dag"],
        "payload": {
            "constraints_patterns": ["multiple valid outputs", "output must satisfy property", "any valid topological order"],
            "generation_strategies": [
                "Implement checker that validates output properties, not string equality",
                "Do not compare output string directly if multiple answers exist",
                "Use quitf(_ok, 'message') and quitf(_wa, 'reason') in testlib checker",
                "For DAG topological sort: checker must (1) verify output is a permutation of [1..n], (2) for every directed edge u->v in original graph, confirm u appears before v in the output sequence",
                "Generate DAGs with many valid topological orderings (sparse edges) to stress checker correctness",
            ],
            "validator_pitfalls": [
                "Using string comparison when multiple answers are valid",
                "Not checking that output satisfies all problem constraints",
                "DAG checker: failing to verify permutation property first — an invalid permutation can falsely pass edge-order checks",
            ],
        },
    },
    {
        "text": "Design checkers for floating-point output with tolerance (eps = 1e-6 or 1e-9)",
        "tags": ["checker", "floating-point", "precision"],
        "payload": {
            "constraints_patterns": ["real-valued output", "absolute/relative error <= 1e-6"],
            "generation_strategies": [
                "Use testlib built-in rcmp6 (1e-6) or rcmp9 (1e-9) for floating-point comparison",
                "Implement custom checker: |expected - actual| <= eps * max(1, |expected|)",
                "Generate tests near zero and near maximum to expose precision issues",
            ],
            "validator_pitfalls": [
                "Direct equality comparison for floats always fails — use tolerance",
                "Not handling NaN or Inf in candidate output",
                "Using too loose a tolerance (1e-3) when problem requires 1e-6",
            ],
        },
    },
    {
        "text": "Generate output-format stress tests: trailing spaces, extra newlines, case sensitivity",
        "tags": ["format", "output", "checker"],
        "payload": {
            "constraints_patterns": ["YES/NO output", "integer sequence output", "single line output"],
            "generation_strategies": [
                "Include test whose correct answer is 'YES' and test whose answer is 'NO'",
                "For problems with 'YES'/'NO' use nyesno checker (case-insensitive)",
                "Include test with output = 0 and output = max_answer",
                "Include test with empty output sequence (answer = 0 elements)",
            ],
            "validator_pitfalls": [
                "Case-sensitive YES/NO check rejects valid 'yes' or 'Yes' answers",
                "Not handling trailing newline in output comparison",
                "Checker crashes on empty output — guard with ouf.eof() check",
            ],
        },
    },

    # ── Category 9: Interval DP ────────────────────────────────────────────
    {
        "text": "Generate interval DP worst-case: matrix chain multiplication with alternating large/small dimensions",
        "tags": ["interval-dp", "overflow", "optimization"],
        "payload": {
            "constraints_patterns": [
                "n matrices, n+1 dimensions", "dim[i] in [1, 1000]",
                "alternating large-small pattern maximizes cost",
            ],
            "generation_strategies": [
                "Alternate dim[i] between 1000 and 1: dims = [1000, 1, 1000, 1, ...]",
                "This prevents any greedy shortcut from reducing cost significantly and maximizes scalar multiplication count",
                "Generate dim[i] = rnd.next(500, 1000) for even i and rnd.next(1, 10) for odd i",
                "For palindrome/sequence DP: generate two strings A, B such that A is a uniform character repeated n times and B uses a completely different character — every LCS DP cell must be computed with no early exit",
            ],
            "validator_pitfalls": [
                "Intermediate product cost can exceed long long for n=500, dim=1000: final cost ~ 500^3/4 * 1000 ~ 3.1e10, fits in int64; but naive unoptimized costs may overflow — validator should assert final answer fits in int64",
                "Not verifying that the number of matrices equals n and dimensions list has exactly n+1 values",
            ],
        },
    },

    # ── Category 10: Anti-Hash ─────────────────────────────────────────────
    {
        "text": "Generate anti-hash strings: Thue-Morse sequence and polynomial hash collision inputs",
        "tags": ["string", "anti-hash", "thue-morse", "hashing"],
        "payload": {
            "constraints_patterns": [
                "string of length n over binary or small alphabet",
                "designed to collide under single-modulus polynomial hashing",
            ],
            "generation_strategies": [
                "Thue-Morse: T[0]='a', T[2k]=T[k], T[2k+1]='b' if T[k]='a' else 'a'; contains no 'cube' (xxx) substring, breaks period-based optimizations",
                "Thue-Morse causes high collision rate under many single-modulus polynomial hashes",
                "For STL unordered_map with integer keys: use multiples of GCC internal bucket-count prime (e.g. all values = k*107897 for k=1..n); all keys hash to bucket 0",
                "For multi-query string problems: generate string S = Thue-Morse of length n; generate Q queries each asking about substrings that are structurally similar — maximizes false-positive rate for naive single-hash solutions",
            ],
            "validator_pitfalls": [
                "Standard validators cannot detect whether a string is 'anti-hash strong' — this is intentional adversarial input and will pass all normal checks",
                "Verify only that string length = n and characters are in allowed set",
            ],
        },
    },

    # ── Category 11: Trie Structures ──────────────────────────────────────
    {
        "text": "Generate Trie space and depth extremes: disjoint prefixes (MLE) and maximal shared prefix (stack depth)",
        "tags": ["tree", "trie", "stress", "stack-overflow"],
        "payload": {
            "constraints_patterns": [
                "set of strings, total length <= max_total",
                "Trie node count <= |sigma| * total_length",
            ],
            "generation_strategies": [
                "MLE case: generate strings such that no two share any prefix; e.g. for alphabet {a..z} use strings 'a'*len, 'b'*len, 'c'*len... — Trie has max nodes = sigma * len",
                "Deep recursion case: generate strings that are prefixes of each other: 'a', 'aa', 'aaa', ..., 'a'*n — Trie is a chain of depth n, triggers stack overflow in DFS implementations",
                "Mixed stress: half the strings share a long common prefix, other half are completely disjoint",
                "Boundary case: single string of maximum allowed length",
            ],
            "validator_pitfalls": [
                "Validate total length of all strings is within sum limit, not just individual string lengths",
                "Check that all characters are within the problem's allowed alphabet",
                "If strings must be distinct, use a set to verify uniqueness",
            ],
        },
    },

    # ── Category 12: Number Theory ─────────────────────────────────────────
    {
        "text": "Generate large prime and semiprime inputs to stress factorization and primality testing",
        "tags": ["number-theory", "primes", "overflow", "stress"],
        "payload": {
            "constraints_patterns": [
                "n up to 10^18", "n = p * q where p, q are large primes",
                "Carmichael numbers for Miller-Rabin stress",
            ],
            "generation_strategies": [
                "Semiprime: generate two primes p, q near sqrt(10^18) ~ 10^9; output n = p * q; this is the hardest case for Pollard's Rho",
                "Large prime: generate a prime close to 10^18 to ensure solution handles the trivial-divisor-free case",
                "Carmichael numbers (e.g. 561, 1105, 2821, 41041): these pass Fermat primality test for all bases not sharing a factor with n, but are composite — stress deterministic Miller-Rabin implementations",
                "Power of prime: n = p^k for large prime p and k >= 2 — tests recursive factorization logic",
                "n = 1: edge case where factorization output should be empty",
            ],
            "validator_pitfalls": [
                "Validator checking primality via trial division will TLE for n ~ 10^18 — must use Miller-Rabin",
                "Validator must ensure p * q does not overflow int64 when generating semiprimes: assert p <= 3e9 and q <= 3e9",
                "Carmichael numbers are valid composite integers — validator should only check 1 <= n <= limit",
            ],
        },
    },

    # ── Category 13: Computational Geometry ───────────────────────────────
    {
        "text": "Generate geometry degenerate cases: collinear points, near-collinear, precision boundary",
        "tags": ["geometry", "precision", "corner_cases"],
        "payload": {
            "constraints_patterns": [
                "n points in 2D", "coordinates in [-10^9, 10^9]",
                "collinear triples trigger convex hull edge cases",
            ],
            "generation_strategies": [
                "Collinear set: generate all points on line y = kx + b; e.g. points (i, 2*i+1) for i=1..n",
                "Near-collinear: take collinear set and add epsilon perturbation to one coordinate — tests if solution uses integer arithmetic or floats",
                "Coincident points: include duplicate coordinates if problem allows — tests degenerate polygon handling",
                "Four points on circle: place points on circumference of a circle with integer radius to trigger Delaunay degeneracy",
                "Maximum coordinate stress: generate points with coordinates at exactly +-10^9, tests long long vs int boundary in cross-product computation",
                "Convex polygon: generate vertices of a regular n-gon (rounded to integers) — convex hull should return all n points",
            ],
            "validator_pitfalls": [
                "Cross product for collinearity check: (b-a) x (c-a) can overflow int if coordinates are 10^9 — must use __int128 or long double in validator",
                "Not handling duplicate points when problem guarantees distinct points",
                "Epsilon comparisons in validator: avoid floating point; prefer integer arithmetic with __int128",
            ],
        },
    },

    # ── Category 14: Multi-Test Engineering ───────────────────────────────
    {
        "text": "Multi-test reset bug: first case max-size, subsequent cases min-size to expose dirty global state",
        "tags": ["engineering", "multi-test", "corner_cases"],
        "payload": {
            "constraints_patterns": [
                "T test cases", "sum of n <= 10^6",
                "first case n=max_n, subsequent cases n=1..10",
            ],
            "generation_strategies": [
                "Generate T=10 cases: first case with n=max_n (fills global arrays with non-zero values), then 9 cases with n in [5, 20]",
                "For array-based problems: ensure values in large case are non-zero and differ from likely default values (0 or -1)",
                "Include a case where the answer is 0 or 'NO' to expose default-value assumptions",
                "Vary the order: also test small-first then large to catch problems that only clear up to current n",
                "Total sum of n should be close to the sum limit to also stress time complexity",
            ],
            "validator_pitfalls": [
                "Validator must check sum-of-n constraint, not just per-case n limit; otherwise TLE masquerades as wrong answer",
                "Check that T is within [1, max_T]",
                "Verify T matches the actual number of test cases in input",
            ],
        },
    },

    # ── Category 15: Adaptive Interaction ─────────────────────────────────
    {
        "text": "Adaptive interactor for interactive problems: maintain candidate set to maximize required queries",
        "tags": ["interactive", "adversarial", "binary-search"],
        "payload": {
            "constraints_patterns": [
                "interactive binary search", "Q queries allowed >= ceil(log2 n)",
                "interactor responds to force maximum queries",
            ],
            "generation_strategies": [
                "Adaptive strategy: do not fix target value upfront; maintain [lo, hi] candidate range; when solver guesses g, always respond with the answer that keeps the larger half: if g <= (lo+hi)/2 respond 'greater', else respond 'less' — only commit when lo==hi",
                "This forces solver to use exactly ceil(log2 n) queries regardless of luck",
                "Generate cases where n is a power of 2 (maximizes required queries for exact log2 n bound)",
                "For 'find the hidden array' style: interactor tracks all constraints from responses and only reveals value when forced, maximizing information entropy across responses",
            ],
            "validator_pitfalls": [
                "Interactor must validate that its responses are consistent with the final committed value — if adaptive strategy is used, double-check that a valid secret value exists consistent with all given responses",
                "If solver outputs illegal format, interactor must return _wa (wrong answer) not _fail (internal error) to avoid polluting evaluation logs",
                "Interactor must flush output after each response: use cout << endl (not '\\n') for interactive problems",
            ],
        },
    },

    # ── Category 16: Validator Meta-Testing ───────────────────────────────
    {
        "text": "Generate invalid test cases to verify validator correctness (meta-testing)",
        "tags": ["validation", "stress", "corner_cases"],
        "payload": {
            "constraints_patterns": [
                "test cases that violate exactly one constraint",
                "used to verify validator rejects invalid input",
            ],
            "generation_strategies": [
                "Generate n = max_n + 1 (one over limit) — validator should reject",
                "Generate valid input then change one value to be out of range",
                "Generate graph with n+1 nodes instead of n",
                "Generate disconnected graph for a problem requiring connectivity",
                "Generate string with one character outside allowed alphabet",
                "Generate negative value where problem requires positive",
                "Systematically violate each constraint exactly once; a correct validator must reject each of these",
            ],
            "validator_pitfalls": [
                "This seed is used to TEST the validator, not the solver — run validator on these inputs and assert all return non-zero exit code",
                "Validators that use assert() will crash on out-of-range; use inf.readInt(lo, hi) from testlib which auto-validates range",
                "Be careful: validator should return _fail for format errors, not _wa — distinguish structural errors from value errors",
            ],
        },
    },

    # ── Category 17: Brute-force + Data Structure Worst Case ──────────────
    {
        "text": "Stress-test with brute-force reference solution and adversarial inputs for common data structures",
        "tags": ["stress", "brute-force", "differential-testing", "adversarial", "algorithm-specific"],
        "payload": {
            "constraints_patterns": ["small n (<=20) for brute force", "random inputs"],
            "generation_strategies": [
                "Generate small random inputs (n <= 20) where brute-force is feasible",
                "Run both optimal and brute-force solutions on same input and compare",
                "If outputs differ, save the failing input as a regression test",
                "Run 1000+ stress iterations to catch probabilistic bugs",
                "Binary search worst case: query always lands on boundary of search space",
                "Two-pointer worst case: array with alternating small/large values forcing many pointer moves",
                "Segment tree worst case: queries always cross the midpoint of the root node ([1, n]) forcing maximum recursion branching; combined with frequent point updates",
                "Hash table worst case: see category 3 (DAG) for unordered_map collision construction",
            ],
            "validator_pitfalls": [
                "Brute-force solution itself may be wrong — verify on public examples first",
                "Small-n stress tests may miss large-n overflow bugs — complement with max-n tests",
                "Segment tree cross-midpoint queries: ensure l <= r and both within [1, n]",
            ],
        },
    },
    # ── Category 18: Articulation Points / Bridges ────────────────────────
    {
        "text": "Generate graphs that stress articulation-point and bridge detection: dandelion, chain-of-rings, biconnected extremes",
        "tags": ["graph", "articulation-point", "bridge", "topology", "special"],
        "payload": {
            "constraints_patterns": [
                "n nodes, m edges", "undirected connected graph",
                "Tarjan DFS tree depth can reach n for chain-of-rings",
            ],
            "generation_strategies": [
                "Dandelion/蒲公英图: build a central cycle of k nodes, then attach n-k leaf chains of random length to random cycle nodes; every cycle node with an attached chain is an articulation point",
                "Chain-of-rings: create t rings each of size s (t*s = n), connect them in a line — the single connecting edge between consecutive rings is a bridge, maximizing bridge count to t-1",
                "Cactus graph: tree where every edge belongs to at most one simple cycle — tests algorithms that distinguish tree-edges from back-edges; create by taking a spanning tree and adding back-edges that each close exactly one cycle",
                "Single articulation point: a star-center with k subtrees attached — removing center disconnects graph into k components",
                "Dense biconnected component: complete graph on sqrt(n) nodes, then connect with bridges to other components — tests that Tarjan correctly identifies biconnected components of varying sizes",
                "All-bridge tree (spanning tree with no back-edges): every edge is a bridge; generated simply as a tree — tests the edge case where bridge count = n-1",
            ],
            "validator_pitfalls": [
                "Must verify graph is connected using BFS/DFS — disconnected input is invalid for most articulation-point problems",
                "Validator should check m is within [n-1, min(max_m, n*(n-1)/2)] to ensure graph is both connected and non-multigraph",
                "Do not allow self-loops or multi-edges unless problem explicitly permits them",
                "For cactus graph validation: independently verify each edge belongs to at most one simple cycle — this requires running the cactus-detection algorithm in the validator itself",
            ],
        },
    },
]
