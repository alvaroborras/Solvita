"""Combined seed items for Hacker System (merged from test_items).

Categories:
 1. Boundary / Constraint
 2. Structural Extremes
 3. Graph Structures
 4. Tree Structures
 5. Arithmetic / Overflow
 6. String
 7. Performance / Stress
 8. Checker / Multi-solution
 9. Interval DP
10. Anti-Hash
11. Trie Structures
12. Number Theory
13. Computational Geometry
14. Multi-Test Engineering
15. Adaptive Interaction
16. Validator Meta-Testing
17. Data Structure Worst Case
"""

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
    },
    {
        "text": "Generate test cases covering constraint boundaries (min/max values)",
        "payload": {
            "adversarial_patterns": ["n=1", "n=max_n", "all values = 0", "all values = max_val", "Include test with minimum n", "Include test with maximum n", "Include test with all elements at boundary values", "Include test with a[i] = 0 alongside max values to test zero-handling branches"],
            "edge_cases": ["Forgetting to check n >= min_n", "Not validating that values are within [min_val, max_val]"]
        },
        "tags": ["boundary", "constraints"]
    },
    {
        "text": "Generate random tests with uniform distribution across constraint range",
        "payload": {
            "adversarial_patterns": ["n in [1, max_n]", "values in [min_val, max_val]", "Use rnd.next() with proper seeding via registerGen", "Generate n uniformly in valid range", "Generate each element uniformly in valid range"],
            "edge_cases": ["Using uninitialized RNG (non-deterministic) \u2014 always use testlib rnd", "Not checking that generated values satisfy constraints"]
        },
        "tags": ["random", "distribution"]
    },
    {
        "text": "Include corner cases: single element, all identical elements, all distinct elements",
        "payload": {
            "adversarial_patterns": ["n=1", "all a[i] equal", "all a[i] distinct", "Generate test with n=1", "Generate test where all elements are the same", "Generate test where all elements are distinct (permutation)", "Generate test with alternating pattern if relevant"],
            "edge_cases": ["Rejecting valid single-element input", "Not handling all-same-value case"]
        },
        "tags": ["corner_cases", "edge"]
    },
    {
        "text": "Generate sorted, reverse-sorted, and near-sorted arrays; also serves as LCS/interval-DP worst case",
        "payload": {
            "adversarial_patterns": ["array sorted ascending", "array sorted descending", "almost sorted", "two completely different alphabets (LCS O(N^2) worst)", "Generate strictly increasing sequence: a[i] = i+1", "Generate strictly decreasing sequence: a[i] = n-i", "Generate nearly sorted: sorted array with k random swaps (k=1..5)", "Generate sawtooth: alternating small/large values", "For LCS worst case: generate A = 'aaa...a' (n zeros), B = 'bbb...b' (n ones) \u2014 zero matches force full DP table traversal", "For palindrome/interval-DP: generate string with no repeated chars to maximize state count"],
            "edge_cases": ["Not verifying that sorted arrays stay within value constraints", "For LCS/palindrome problems: not checking both strings have correct length"]
        },
        "tags": ["sorted", "structural", "stress", "interval-dp"]
    },
    {
        "text": "Generate permutations: identity, reversed, and random shuffles",
        "payload": {
            "adversarial_patterns": ["permutation of [1..n]", "all values distinct", "values in [1, n]", "Generate identity permutation: a[i] = i", "Generate reversed permutation: a[i] = n+1-i", "Use rnd.shuffle() for random permutation", "Generate cyclic shift: a[i] = (i % n) + 1"],
            "edge_cases": ["Not verifying all values in [1, n] are present exactly once", "Allowing duplicate values in a permutation"]
        },
        "tags": ["permutation", "structural"]
    },
    {
        "text": "For graph problems, generate connected and disconnected graphs",
        "payload": {
            "adversarial_patterns": ["m edges", "n nodes", "connected vs disconnected", "Generate spanning tree first to ensure connectivity, then add random edges", "Generate disconnected graph by creating separate components", "Ensure no self-loops and no multi-edges unless explicitly allowed"],
            "edge_cases": ["Not checking that edges are within [1, n]", "Allowing self-loops or multi-edges if not permitted"]
        },
        "tags": ["graph", "connectivity"]
    },
    {
        "text": "Generate special graph topologies: chain, star, complete graph, bipartite; also SPFA adversarial grid",
        "payload": {
            "adversarial_patterns": ["chain: n-1 edges", "star: degree-n-1 center", "complete: n*(n-1)/2 edges", "grid graph with back edges for SPFA hack", "Chain/path graph: edge i-(i+1) for i in [1, n-1]", "Star graph: center=1, edges 1-i for i in [2, n]", "Complete graph: all pairs (i, j) for i < j (only for small n \u2264 500)", "Bipartite: partition vertices into two sets A, B; edges only between sets", "SPFA hack: construct a vertical chain with cheap downward edges and expensive horizontal cross-edges; add selective back-edges to force repeated node relaxation", "SPFA hack detail: each node re-enters queue O(n) times, degrading to O(VE) worst case"],
            "edge_cases": ["Complete graph on large n exceeds edge limit \u2014 guard with n*(n-1)/2 <= max_m", "SPFA hack graphs often contain negative edges \u2014 validate absence of negative cycles unless problem allows"]
        },
        "tags": ["graph", "topology", "special", "adversarial", "shortest-path"]
    },
    {
        "text": "Generate DAGs and directed graphs; include adversarial unordered_map hash collision inputs",
        "payload": {
            "adversarial_patterns": ["directed edges u->v with u < v for DAG", "integer keys that are multiples of GCC hashtable primes", "DAG: assign topological order, add edges only from lower to higher index", "Random DAG: for each pair (u, v) with u < v, add edge with probability p", "Ensure DAG is connected (weakly) by adding chain edges first", "unordered_map collision: GCC uses internal primes (126271, 107897...) as bucket counts; generate keys that are all multiples of one such prime so every key lands in bucket 0, degrading insertion to O(n) per operation", "Concretely: output n, then 1*107897, 2*107897, ..., n*107897 as the key sequence"],
            "edge_cases": ["Back edges violate DAG property \u2014 validate with topological sort", "Hash collision inputs are Valid but Malicious \u2014 standard range checks cannot detect them; document this as an intentional adversarial seed"]
        },
        "tags": ["graph", "DAG", "directed", "stl", "hashing", "collision"]
    },
    {
        "text": "Generate special tree structures: bamboo (chain), star, caterpillar, random tree, complete binary",
        "payload": {
            "adversarial_patterns": ["n nodes", "n-1 edges", "connected acyclic", "Bamboo/chain tree: parent[i] = i-1 for i in [2, n] \u2014 triggers stack overflow in recursive DFS", "Star tree: parent[i] = 1 for all i in [2, n] \u2014 maximizes degree-1 aggregation in tree DP", "Random tree: rnd.wnext(i-1, t) for positive t gives chain-biased, negative t gives star-biased trees", "Caterpillar: build main chain of length n/2, then attach remaining nodes to random positions on chain \u2014 mixes deep recursion with high-degree aggregation", "Complete binary tree: parent[i] = i//2", "For tree DP: bamboo tests information propagation distance; star tests single-node aggregation cost", "After generating parent array, shuffle node labels via rnd.perm(n) to hide topology from solvers"],
            "edge_cases": ["Tree must have exactly n-1 edges and be connected \u2014 verify both with DSU or BFS", "Parent array must not create cycles: in Prufer-free construction ensure parent[i] < i before shuffle", "Check that shuffled edge list still forms a valid tree after relabeling"]
        },
        "tags": ["tree", "special", "stack-overflow"]
    },
    {
        "text": "Generate arithmetic overflow stress tests: values near INT64 boundaries",
        "payload": {
            "adversarial_patterns": ["values up to 1e18", "products may exceed int64", "a*b overflow risk", "Include test with a[i] = 10^18 (maximum int64-safe value)", "Include test with a[i] = -10^18 for signed problems", "Generate pairs (a, b) where a*b would overflow int64 \u2014 tests __int128 usage", "For interval DP (e.g. matrix chain): alternate dim[i] between 1000 and 1 \u2014 maximizes intermediate products; final cost may exceed int64 if unchecked", "Generate a[i] = 0 alongside max values to test zero-handling branches"],
            "edge_cases": ["Not validating that values fit in long long (int64)", "Allowing values that cause intermediate overflow in the validator itself", "For interval DP: independently compute minimum cost and assert it fits in long long before accepting the test"]
        },
        "tags": ["overflow", "arithmetic", "numeric"]
    },
    {
        "text": "Generate tests with negative numbers, zeros, and mixed-sign arrays",
        "payload": {
            "adversarial_patterns": ["values in [-max_val, max_val]", "can be zero", "mixed positive/negative", "Generate all-negative array: a[i] = -rnd.next(1, max_val)", "Generate array with exactly one zero and rest positive", "Generate alternating positive/negative", "Generate array summing to zero (cancellation test)"],
            "edge_cases": ["Not allowing negative values when problem permits them", "Assuming all values are positive without checking constraints"]
        },
        "tags": ["negative", "numeric", "mixed"]
    },
    {
        "text": "For string problems, include strings with special characters and edge lengths",
        "payload": {
            "adversarial_patterns": ["length in [1, max_len]", "allowed character set", "Generate string of length 1", "Generate string of maximum length", "Include strings with only one unique character (e.g., 'aaa...a')", "Include strings using only first and last characters of the allowed set", "Include strings where every character appears exactly once"],
            "edge_cases": ["Not checking string length bounds", "Allowing characters outside permitted character set"]
        },
        "tags": ["string", "characters"]
    },
    {
        "text": "Generate palindromes, periodic strings, and Fibonacci strings to stress KMP/Z-algorithm/suffix array",
        "payload": {
            "adversarial_patterns": ["string of length n", "characters from given alphabet", "Palindrome: generate first half randomly, mirror to second half", "Periodic string: repeat base pattern of length k, period divides n", "All-same: s = 'a' * n", "Fibonacci string: S0='a', S1='b', S_i = S_{i-1} + S_{i-2}; contains maximum number of distinct border lengths, maximizes KMP fail-pointer back-jumps and Z-algorithm comparisons", "Almost-palindrome: palindrome with one character changed at center", "Anti-period: string 'aaa...aab' (pattern length n, last char different) forces KMP to traverse all fail pointers before mismatch"],
            "edge_cases": ["Palindrome construction must handle odd-length strings correctly", "Fibonacci string grows exponentially \u2014 generate up to n characters then truncate; validator must check exact length", "Not verifying that periodic string length is exactly n"]
        },
        "tags": ["string", "palindrome", "periodic", "kmp", "stress"]
    },
    {
        "text": "Validate input format strictly: correct number of tokens, valid separators",
        "payload": {
            "adversarial_patterns": ["expected number of lines", "expected tokens per line", "Count tokens and validate against expected format", "Check for extra whitespace or missing newlines", "Use inf.readEoln() and inf.readEof() in testlib validator"],
            "edge_cases": ["Not checking for trailing whitespace", "Accepting input with wrong number of elements", "Forgetting inf.readEof() at end of validator"]
        },
        "tags": ["validation", "format"]
    },
    {
        "text": "Generate large worst-case tests including Dinic layered graph and segment tree cross-midpoint queries",
        "payload": {
            "adversarial_patterns": ["n = max_n", "worst-case complexity", "layered graph for flow", "Generate test with maximum n", "Generate worst-case for expected algorithm: sorted array for naive sort, chain graph for DFS", "For DP problems: maximize depth of recursion / state space", "Dinic layered graph: construct K layers each of size L (K*L ~ n); every node in layer i connects to every node in layer i+1 with capacity 1; this forces O(K) blocking flow rounds each scanning O(K*L^2) edges, approaching O(V^2 E) worst case", "Segment tree cross-midpoint queries: generate queries [l, r] such that l is near the right end of the left subtree and r is near the left end of the right subtree, forcing maximum recursion branching at every level", "Dense graph (m \u2248 max_m) for graph problems"],
            "edge_cases": ["Not testing with maximum constraints", "Generator or validator timing out on large input (keep generator O(n))", "Dinic layered graph: ensure source/sink are distinct and no self-loops"]
        },
        "tags": ["performance", "stress", "flow", "adversarial"]
    },
    {
        "text": "Use checker to verify output correctness for problems with multiple valid answers including DAG topological order",
        "payload": {
            "adversarial_patterns": ["multiple valid outputs", "output must satisfy property", "any valid topological order", "Implement checker that validates output properties, not string equality", "Do not compare output string directly if multiple answers exist", "Use quitf(_ok, 'message') and quitf(_wa, 'reason') in testlib checker", "For DAG topological sort: checker must (1) verify output is a permutation of [1..n], (2) for every directed edge u->v in original graph, confirm u appears before v in the output sequence", "Generate DAGs with many valid topological orderings (sparse edges) to stress checker correctness"],
            "edge_cases": ["Using string comparison when multiple answers are valid", "Not checking that output satisfies all problem constraints", "DAG checker: failing to verify permutation property first \u2014 an invalid permutation can falsely pass edge-order checks"]
        },
        "tags": ["checker", "multi-solution", "dag"]
    },
    {
        "text": "Design checkers for floating-point output with tolerance (eps = 1e-6 or 1e-9)",
        "payload": {
            "adversarial_patterns": ["real-valued output", "absolute/relative error <= 1e-6", "Use testlib built-in rcmp6 (1e-6) or rcmp9 (1e-9) for floating-point comparison", "Implement custom checker: |expected - actual| <= eps * max(1, |expected|)", "Generate tests near zero and near maximum to expose precision issues"],
            "edge_cases": ["Direct equality comparison for floats always fails \u2014 use tolerance", "Not handling NaN or Inf in candidate output", "Using too loose a tolerance (1e-3) when problem requires 1e-6"]
        },
        "tags": ["checker", "floating-point", "precision"]
    },
    {
        "text": "Generate output-format stress tests: trailing spaces, extra newlines, case sensitivity",
        "payload": {
            "adversarial_patterns": ["YES/NO output", "integer sequence output", "single line output", "Include test whose correct answer is 'YES' and test whose answer is 'NO'", "For problems with 'YES'/'NO' use nyesno checker (case-insensitive)", "Include test with output = 0 and output = max_answer", "Include test with empty output sequence (answer = 0 elements)"],
            "edge_cases": ["Case-sensitive YES/NO check rejects valid 'yes' or 'Yes' answers", "Not handling trailing newline in output comparison", "Checker crashes on empty output \u2014 guard with ouf.eof() check"]
        },
        "tags": ["format", "output", "checker"]
    },
    {
        "text": "Generate interval DP worst-case: matrix chain multiplication with alternating large/small dimensions",
        "payload": {
            "adversarial_patterns": ["n matrices, n+1 dimensions", "dim[i] in [1, 1000]", "alternating large-small pattern maximizes cost", "Alternate dim[i] between 1000 and 1: dims = [1000, 1, 1000, 1, ...]", "This prevents any greedy shortcut from reducing cost significantly and maximizes scalar multiplication count", "Generate dim[i] = rnd.next(500, 1000) for even i and rnd.next(1, 10) for odd i", "For palindrome/sequence DP: generate two strings A, B such that A is a uniform character repeated n times and B uses a completely different character \u2014 every LCS DP cell must be computed with no early exit"],
            "edge_cases": ["Intermediate product cost can exceed long long for n=500, dim=1000: final cost ~ 500^3/4 * 1000 ~ 3.1e10, fits in int64; but naive unoptimized costs may overflow \u2014 validator should assert final answer fits in int64", "Not verifying that the number of matrices equals n and dimensions list has exactly n+1 values"]
        },
        "tags": ["interval-dp", "overflow", "optimization"]
    },
    {
        "text": "Generate anti-hash strings: Thue-Morse sequence and polynomial hash collision inputs",
        "payload": {
            "adversarial_patterns": ["string of length n over binary or small alphabet", "designed to collide under single-modulus polynomial hashing", "Thue-Morse: T[0]='a', T[2k]=T[k], T[2k+1]='b' if T[k]='a' else 'a'; contains no 'cube' (xxx) substring, breaks period-based optimizations", "Thue-Morse causes high collision rate under many single-modulus polynomial hashes", "For STL unordered_map with integer keys: use multiples of GCC internal bucket-count prime (e.g. all values = k*107897 for k=1..n); all keys hash to bucket 0", "For multi-query string problems: generate string S = Thue-Morse of length n; generate Q queries each asking about substrings that are structurally similar \u2014 maximizes false-positive rate for naive single-hash solutions"],
            "edge_cases": ["Standard validators cannot detect whether a string is 'anti-hash strong' \u2014 this is intentional adversarial input and will pass all normal checks", "Verify only that string length = n and characters are in allowed set"]
        },
        "tags": ["string", "anti-hash", "thue-morse", "hashing"]
    },
    {
        "text": "Generate Trie space and depth extremes: disjoint prefixes (MLE) and maximal shared prefix (stack depth)",
        "payload": {
            "adversarial_patterns": ["set of strings, total length <= max_total", "Trie node count <= |sigma| * total_length", "MLE case: generate strings such that no two share any prefix; e.g. for alphabet {a..z} use strings 'a'*len, 'b'*len, 'c'*len... \u2014 Trie has max nodes = sigma * len", "Deep recursion case: generate strings that are prefixes of each other: 'a', 'aa', 'aaa', ..., 'a'*n \u2014 Trie is a chain of depth n, triggers stack overflow in DFS implementations", "Mixed stress: half the strings share a long common prefix, other half are completely disjoint", "Boundary case: single string of maximum allowed length"],
            "edge_cases": ["Validate total length of all strings is within sum limit, not just individual string lengths", "Check that all characters are within the problem's allowed alphabet", "If strings must be distinct, use a set to verify uniqueness"]
        },
        "tags": ["tree", "trie", "stress", "stack-overflow"]
    },
    {
        "text": "Generate large prime and semiprime inputs to stress factorization and primality testing",
        "payload": {
            "adversarial_patterns": ["n up to 10^18", "n = p * q where p, q are large primes", "Carmichael numbers for Miller-Rabin stress", "Semiprime: generate two primes p, q near sqrt(10^18) ~ 10^9; output n = p * q; this is the hardest case for Pollard's Rho", "Large prime: generate a prime close to 10^18 to ensure solution handles the trivial-divisor-free case", "Carmichael numbers (e.g. 561, 1105, 2821, 41041): these pass Fermat primality test for all bases not sharing a factor with n, but are composite \u2014 stress deterministic Miller-Rabin implementations", "Power of prime: n = p^k for large prime p and k >= 2 \u2014 tests recursive factorization logic", "n = 1: edge case where factorization output should be empty"],
            "edge_cases": ["Validator checking primality via trial division will TLE for n ~ 10^18 \u2014 must use Miller-Rabin", "Validator must ensure p * q does not overflow int64 when generating semiprimes: assert p <= 3e9 and q <= 3e9", "Carmichael numbers are valid composite integers \u2014 validator should only check 1 <= n <= limit"]
        },
        "tags": ["number-theory", "primes", "overflow", "stress"]
    },
    {
        "text": "Generate geometry degenerate cases: collinear points, near-collinear, precision boundary",
        "payload": {
            "adversarial_patterns": ["n points in 2D", "coordinates in [-10^9, 10^9]", "collinear triples trigger convex hull edge cases", "Collinear set: generate all points on line y = kx + b; e.g. points (i, 2*i+1) for i=1..n", "Near-collinear: take collinear set and add epsilon perturbation to one coordinate \u2014 tests if solution uses integer arithmetic or floats", "Coincident points: include duplicate coordinates if problem allows \u2014 tests degenerate polygon handling", "Four points on circle: place points on circumference of a circle with integer radius to trigger Delaunay degeneracy", "Maximum coordinate stress: generate points with coordinates at exactly +-10^9, tests long long vs int boundary in cross-product computation", "Convex polygon: generate vertices of a regular n-gon (rounded to integers) \u2014 convex hull should return all n points"],
            "edge_cases": ["Cross product for collinearity check: (b-a) x (c-a) can overflow int if coordinates are 10^9 \u2014 must use __int128 or long double in validator", "Not handling duplicate points when problem guarantees distinct points", "Epsilon comparisons in validator: avoid floating point; prefer integer arithmetic with __int128"]
        },
        "tags": ["geometry", "precision", "corner_cases"]
    },
    {
        "text": "Multi-test reset bug: first case max-size, subsequent cases min-size to expose dirty global state",
        "payload": {
            "adversarial_patterns": ["T test cases", "sum of n <= 10^6", "first case n=max_n, subsequent cases n=1..10", "Generate T=10 cases: first case with n=max_n (fills global arrays with non-zero values), then 9 cases with n in [5, 20]", "For array-based problems: ensure values in large case are non-zero and differ from likely default values (0 or -1)", "Include a case where the answer is 0 or 'NO' to expose default-value assumptions", "Vary the order: also test small-first then large to catch problems that only clear up to current n", "Total sum of n should be close to the sum limit to also stress time complexity"],
            "edge_cases": ["Validator must check sum-of-n constraint, not just per-case n limit; otherwise TLE masquerades as wrong answer", "Check that T is within [1, max_T]", "Verify T matches the actual number of test cases in input"]
        },
        "tags": ["engineering", "multi-test", "corner_cases"]
    },
    {
        "text": "Adaptive interactor for interactive problems: maintain candidate set to maximize required queries",
        "payload": {
            "adversarial_patterns": ["interactive binary search", "Q queries allowed >= ceil(log2 n)", "interactor responds to force maximum queries", "Adaptive strategy: do not fix target value upfront; maintain [lo, hi] candidate range; when solver guesses g, always respond with the answer that keeps the larger half: if g <= (lo+hi)/2 respond 'greater', else respond 'less' \u2014 only commit when lo==hi", "This forces solver to use exactly ceil(log2 n) queries regardless of luck", "Generate cases where n is a power of 2 (maximizes required queries for exact log2 n bound)", "For 'find the hidden array' style: interactor tracks all constraints from responses and only reveals value when forced, maximizing information entropy across responses"],
            "edge_cases": ["Interactor must validate that its responses are consistent with the final committed value \u2014 if adaptive strategy is used, double-check that a valid secret value exists consistent with all given responses", "If solver outputs illegal format, interactor must return _wa (wrong answer) not _fail (internal error) to avoid polluting evaluation logs", "Interactor must flush output after each response: use cout << endl (not '\\n') for interactive problems"]
        },
        "tags": ["interactive", "adversarial", "binary-search"]
    },
    {
        "text": "Generate invalid test cases to verify validator correctness (meta-testing)",
        "payload": {
            "adversarial_patterns": ["test cases that violate exactly one constraint", "used to verify validator rejects invalid input", "Generate n = max_n + 1 (one over limit) \u2014 validator should reject", "Generate valid input then change one value to be out of range", "Generate graph with n+1 nodes instead of n", "Generate disconnected graph for a problem requiring connectivity", "Generate string with one character outside allowed alphabet", "Generate negative value where problem requires positive", "Systematically violate each constraint exactly once; a correct validator must reject each of these"],
            "edge_cases": ["This seed is used to TEST the validator, not the solver \u2014 run validator on these inputs and assert all return non-zero exit code", "Validators that use assert() will crash on out-of-range; use inf.readInt(lo, hi) from testlib which auto-validates range", "Be careful: validator should return _fail for format errors, not _wa \u2014 distinguish structural errors from value errors"]
        },
        "tags": ["validation", "stress", "corner_cases"]
    },
    {
        "text": "Stress-test with brute-force reference solution and adversarial inputs for common data structures",
        "payload": {
            "adversarial_patterns": ["small n (<=20) for brute force", "random inputs", "Generate small random inputs (n <= 20) where brute-force is feasible", "Run both optimal and brute-force solutions on same input and compare", "If outputs differ, save the failing input as a regression test", "Run 1000+ stress iterations to catch probabilistic bugs", "Binary search worst case: query always lands on boundary of search space", "Two-pointer worst case: array with alternating small/large values forcing many pointer moves", "Segment tree worst case: queries always cross the midpoint of the root node ([1, n]) forcing maximum recursion branching; combined with frequent point updates", "Hash table worst case: see category 3 (DAG) for unordered_map collision construction"],
            "edge_cases": ["Brute-force solution itself may be wrong \u2014 verify on public examples first", "Small-n stress tests may miss large-n overflow bugs \u2014 complement with max-n tests", "Segment tree cross-midpoint queries: ensure l <= r and both within [1, n]"]
        },
        "tags": ["stress", "brute-force", "differential-testing", "adversarial", "algorithm-specific"]
    },
    {
        "text": "Generate graphs that stress articulation-point and bridge detection: dandelion, chain-of-rings, biconnected extremes",
        "payload": {
            "adversarial_patterns": ["n nodes, m edges", "undirected connected graph", "Tarjan DFS tree depth can reach n for chain-of-rings", "Dandelion/\u84b2\u516c\u82f1\u56fe: build a central cycle of k nodes, then attach n-k leaf chains of random length to random cycle nodes; every cycle node with an attached chain is an articulation point", "Chain-of-rings: create t rings each of size s (t*s = n), connect them in a line \u2014 the single connecting edge between consecutive rings is a bridge, maximizing bridge count to t-1", "Cactus graph: tree where every edge belongs to at most one simple cycle \u2014 tests algorithms that distinguish tree-edges from back-edges; create by taking a spanning tree and adding back-edges that each close exactly one cycle", "Single articulation point: a star-center with k subtrees attached \u2014 removing center disconnects graph into k components", "Dense biconnected component: complete graph on sqrt(n) nodes, then connect with bridges to other components \u2014 tests that Tarjan correctly identifies biconnected components of varying sizes", "All-bridge tree (spanning tree with no back-edges): every edge is a bridge; generated simply as a tree \u2014 tests the edge case where bridge count = n-1"],
            "edge_cases": ["Must verify graph is connected using BFS/DFS \u2014 disconnected input is invalid for most articulation-point problems", "Validator should check m is within [n-1, min(max_m, n*(n-1)/2)] to ensure graph is both connected and non-multigraph", "Do not allow self-loops or multi-edges unless problem explicitly permits them", "For cactus graph validation: independently verify each edge belongs to at most one simple cycle \u2014 this requires running the cactus-detection algorithm in the validator itself"]
        },
        "tags": ["graph", "articulation-point", "bridge", "topology", "special"]
    }
]
