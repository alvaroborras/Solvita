"""Seed items for Oracle (TestGen Brute-Force) memory.

Extracted concepts from C++17 暴力算法模板库构建.md
"""

from typing import Dict, Any, List

ORACLE_SEED_ITEMS: List[Dict[str, Any]] = [
    {
        "text": "N-Nested Loops Simulation (Dynamic Depth DFS)",
        "payload": {
            "brute_force_strategies": ["Dynamic Depth DFS for arbitrary variables"],
            "complexity_notes": ["O(R^N) where R is range of each variable"],
            "code_template": """
#include <iostream>
#include <vector>
#include <functional>

using ll = long long;

void n_nested_loops(const std::vector<ll>& ranges, 
                    const std::function<void(const std::vector<ll>&)>& process) {
    ll n = ranges.size();
    std::vector<ll> current_state(n, 0);
    
    std::function<void(ll)> simulate = [&](ll depth) {
        if (depth == n) {
            process(current_state);
            return;
        }
        for (ll i = 0; i < ranges[depth]; ++i) {
            current_state[depth] = i;
            simulate(depth + 1);
        }
    };
    simulate(0);
}
            """
        },
        "tags": ["core", "brute_force", "oracle", "nested_loops"]
    },
    {
        "text": "All Paths DFS Traversal (Graph/Grid)",
        "payload": {
            "brute_force_strategies": ["Complete Path Enumeration via DFS"],
            "complexity_notes": ["O(V!) in fully connected graph worst case"],
            "code_template": """
#include <vector>
using ll = long long;

std::vector<std::vector<ll>> find_all_paths(const std::vector<std::vector<ll>>& graph, ll source, ll target) {
    std::vector<std::vector<ll>> all_paths;
    std::vector<ll> current_path;
    std::vector<bool> visited(graph.size(), false);
    
    std::function<void(ll)> dfs_backtrack = [&](ll u) {
        current_path.push_back(u);
        visited[u] = true;
        if (u == target) {
            all_paths.push_back(current_path);
        } else {
            for (ll v : graph[u]) {
                if (!visited[v]) dfs_backtrack(v);
            }
        }
        visited[u] = false;
        current_path.pop_back();
    };
    dfs_backtrack(source);
    return all_paths;
}
            """
        },
        "tags": ["core", "brute_force", "oracle", "graph_dfs"]
    },
    {
        "text": "Minimax with Memoization (Game Theory)",
        "payload": {
            "brute_force_strategies": ["Minimax Game Tree Search with unordered_map memoization"],
            "complexity_notes": ["O(b^d) without memo, reduces significantly with state merging"],
            "code_template": """
#include <iostream>
#include <unordered_map>
#include <vector>
#include <functional>

struct GameState {
    int stick_count;
    bool operator==(const GameState& o) const { return stick_count == o.stick_count; }
};
struct StateHash {
    size_t operator()(const GameState& s) const { return std::hash<int>()(s.stick_count); }
};

int solve_minimax() {
    std::unordered_map<GameState, int, StateHash> memo;
    std::function<int(GameState, bool)> minimax = [&](GameState state, bool is_max_turn) -> int {
        if (state.stick_count == 0) return is_max_turn ? -1 : 1;
        if (memo.count(state)) return memo[state];
        
        int best_val = is_max_turn ? -1e9 : 1e9;
        for (int take : {1, 2, 3}) {
            if (state.stick_count >= take) {
                GameState next_state{state.stick_count - take};
                int val = minimax(next_state, !is_max_turn);
                best_val = is_max_turn ? std::max(best_val, val) : std::min(best_val, val);
            }
        }
        return memo[state] = best_val;
    };
    return minimax(GameState{10}, true);
}
            """
        },
        "tags": ["core", "brute_force", "oracle", "minimax"]
    },
    {
        "text": "Top-down Memoized DP",
        "payload": {
            "brute_force_strategies": ["Exponential State Space to Polynomial via Top-Down DP"],
            "complexity_notes": ["O(StateSpace). Filters invalid states directly."],
            "code_template": """
#include <vector>
#include <functional>
using ll = long long;

ll knapsack_topdown(const std::vector<ll>& wt, const std::vector<ll>& val, ll W) {
    ll n = wt.size();
    std::vector<std::vector<ll>> memo(n, std::vector<ll>(W + 1, -1));
    
    std::function<ll(ll, ll)> solve = [&](ll i, ll rem_w) -> ll {
        if (i < 0 || rem_w == 0) return 0;
        if (memo[i][rem_w] != -1) return memo[i][rem_w];
        if (wt[i] > rem_w) return memo[i][rem_w] = solve(i - 1, rem_w);
        return memo[i][rem_w] = std::max(solve(i - 1, rem_w), val[i] + solve(i - 1, rem_w - wt[i]));
    };
    return solve(n - 1, W);
}
            """
        },
        "tags": ["core", "brute_force", "oracle", "dp"]
    },
    {
        "text": "Combinatorial Enum & Set Partitions (Bell Numbers)",
        "payload": {
            "brute_force_strategies": ["Enumerating all Set Partitions via Backtracking"],
            "complexity_notes": ["O(B_n) where B_n is the n-th Bell Number"],
            "code_template": """
#include <vector>
using ll = long long;

void generate_partitions(ll n, const std::function<void(const std::vector<std::vector<ll>>&)>& process) {
    std::vector<std::vector<ll>> current_partition;
    std::function<void(ll)> backtrack = [&](ll element) {
        if (element == n) { process(current_partition); return; }
        for (size_t i = 0; i < current_partition.size(); ++i) {
            current_partition[i].push_back(element);
            backtrack(element + 1);
            current_partition[i].pop_back();
        }
        current_partition.push_back({element});
        backtrack(element + 1);
        current_partition.pop_back();
    };
    backtrack(0);
}
            """
        },
        "tags": ["core", "brute_force", "oracle", "combinatorics"]
    },
    {
        "text": "Meet-in-the-Middle (Subset Sum)",
        "payload": {
            "brute_force_strategies": ["Split State Space & Binary Search"],
            "complexity_notes": ["O(N * 2^(N/2)) - highly effective for N <= 40"],
            "code_template": """
#include <vector>
#include <algorithm>
using ll = long long;

ll meet_in_the_middle(const std::vector<ll>& A, ll S) {
    ll n = A.size();
    auto get_subsets = [&](ll l, ll r) {
        std::vector<ll> res;
        ll len = r - l + 1;
        for (ll mask = 0; mask < (1LL << len); ++mask) {
            ll sum = 0;
            for (ll i = 0; i < len; ++i) if (mask & (1LL << i)) sum += A[l + i];
            res.push_back(sum);
        }
        return res;
    };
    std::vector<ll> left = get_subsets(0, n / 2 - 1);
    std::vector<ll> right = get_subsets(n / 2, n - 1);
    std::sort(right.begin(), right.end());
    
    ll max_valid = -1;
    for (ll v : left) {
        if (v > S) continue;
        auto it = std::upper_bound(right.begin(), right.end(), S - v);
        if (it != right.begin()) {
            max_valid = std::max(max_valid, v + *std::prev(it));
        }
    }
    return max_valid;
}
            """
        },
        "tags": ["extended", "brute_force", "oracle", "meet_in_the_middle"]
    },
    {
        "text": "String Subsequences (Bitmask Simulation)",
        "payload": {
            "brute_force_strategies": ["Binary Counting up to 2^N to extract sequence shapes"],
            "complexity_notes": ["O(N * 2^N) - suitable for string lengths N <= 20"],
            "code_template": """
#include <string>
#include <vector>
using namespace std;

void generate_subsequences(const string& s, auto process) {
    int n = s.length();
    for(int mask = 0; mask < (1 << n); mask++) {
        string sub = "";
        for(int i = 0; i < n; i++) {
            if(mask & (1 << i)) sub += s[i];
        }
        process(sub);
    }
}
            """
        },
        "tags": ["extended", "brute_force", "oracle", "string_subsequences"]
    },
    {
        "text": "Geometry Triplets & Exhaustive Enumeration",
        "payload": {
            "brute_force_strategies": ["O(N^3) Nested Iteration with Collinearity Checks"],
            "complexity_notes": ["N<=500 limits for brute force geometry bounds"],
            "code_template": """
#include <vector>
using namespace std;
struct Point { long long x, y; };

long long cross_product(Point o, Point a, Point b) {
    return (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
}

void exhaust_triplets(const vector<Point>& pts, auto process) {
    int n = pts.size();
    for(int i = 0; i < n; i++) {
        for(int j = i+1; j < n; j++) {
            for(int k = j+1; k < n; k++) {
                if (cross_product(pts[i], pts[j], pts[k]) != 0) {
                    process(pts[i], pts[j], pts[k]);
                }
            }
        }
    }
}
            """
        },
        "tags": ["extended", "brute_force", "oracle", "geometry"]
    },
    {
        "text": "Bitmask SOS Subset Sum Enumeration",
        "payload": {
            "brute_force_strategies": ["Sum Over Subsets (SOS) for subset transitions"],
            "complexity_notes": ["O(3^N) Exact subset enumeration of a bitmask"],
            "code_template": """
#include <vector>
using namespace std;
void subset_enumeration(int n, auto process) {
    for(int mask = 0; mask < (1 << n); mask++) {
        // Enumerate all subsets of 'mask'
        for(int sub = mask; sub > 0; sub = (sub - 1) & mask) {
            process(mask, sub);
        }
    }
}
            """
        },
        "tags": ["extended", "brute_force", "oracle", "bitmask"]
    },
    {
        "text": "VectorStateHash and PairStateHash (Custom Hashing for DFS Memory)",
        "payload": {
            "brute_force_strategies": ["Hash Combiner using Boost's magic constant (0x9e3779b9)"],
            "complexity_notes": ["Prevent C++ unordered_map MLE (Memory Limit Exceeded) due to weak hashing"],
            "code_template": """
#include <cstddef>
#include <vector>

// Magic Hash Combiner (Borrowed from Boost)
template <class T>
inline void hash_combine(std::size_t& seed, const T& v) {
    std::hash<T> hasher;
    seed ^= hasher(v) + 0x9e3779b9 + (seed<<6) + (seed>>2);
}

// Hashing a dynamic Vector State for unorded_map caching
struct VectorStateHash {
    std::size_t operator()(const std::vector<long long>& v) const {
        std::size_t seed = 0;
        for (auto& i : v) {
            hash_combine(seed, i);
        }
        return seed;
    }
};

// Hashing Pair States
struct PairHash {
    template <class T1, class T2>
    std::size_t operator()(const std::pair<T1, T2>& p) const {
        std::size_t seed = 0;
        hash_combine(seed, p.first);
        hash_combine(seed, p.second);
        return seed;
    }
};
            """
        },
        "tags": ["hash", "brute_force", "oracle", "custom_hash"]
    }
]
