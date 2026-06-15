const SOLUTIONS: Record<string, string> = {
  showcase_bfs_shortest_path: `#include <iostream>
#include <queue>
#include <vector>

int main() {
    std::ios::sync_with_stdio(false);
    std::cin.tie(nullptr);

    int n, m;
    std::cin >> n >> m;
    std::vector<std::vector<int>> graph(n + 1);
    for (int i = 0; i < m; ++i) {
        int u, v;
        std::cin >> u >> v;
        graph[u].push_back(v);
        graph[v].push_back(u);
    }

    std::vector<int> dist(n + 1, -1);
    std::queue<int> q;
    dist[1] = 0;
    q.push(1);

    while (!q.empty()) {
        int u = q.front();
        q.pop();
        for (int v : graph[u]) {
            if (dist[v] != -1) continue;
            dist[v] = dist[u] + 1;
            q.push(v);
        }
    }

    std::cout << dist[n] << '\\n';
    return 0;
}
`,
  showcase_dfs_subtree_size: `#include <iostream>
#include <vector>

void dfs(int u, int parent, const std::vector<std::vector<int>>& tree, int& count) {
    ++count;
    for (int v : tree[u]) {
        if (v == parent) continue;
        dfs(v, parent = u, tree, count);
    }
}

int main() {
    std::ios::sync_with_stdio(false);
    std::cin.tie(nullptr);

    int n;
    std::cin >> n;
    std::vector<std::vector<int>> tree(n + 1);
    for (int i = 0; i < n - 1; ++i) {
        int u, v;
        std::cin >> u >> v;
        tree[u].push_back(v);
        tree[v].push_back(u);
    }

    int subtree_size = 0;
    dfs(1, 0, tree, subtree_size);
    std::cout << subtree_size << '\\n';
    return 0;
}
`,
  showcase_dp_grid_path_sum: `#include <algorithm>
#include <iostream>
#include <vector>

int main() {
    std::ios::sync_with_stdio(false);
    std::cin.tie(nullptr);

    int n, m;
    std::cin >> n >> m;
    std::vector<std::vector<long long>> dp(n, std::vector<long long>(m, 0));

    for (int i = 0; i < n; ++i) {
        for (int j = 0; j < m; ++j) {
            long long value;
            std::cin >> value;
            long long best = value;
            if (i > 0) best = std::max(best, dp[i - 1][j] + value);
            if (j > 0) best = std::max(best, dp[i][j - 1] + value);
            dp[i][j] = best;
        }
    }

    std::cout << dp[n - 1][m - 1] << '\\n';
    return 0;
}
`,
  showcase_two_pointers_pair_sum: `#include <iostream>
#include <vector>

int main() {
    std::ios::sync_with_stdio(false);
    std::cin.tie(nullptr);

    int n;
    std::cin >> n;
    std::vector<long long> a(n);
    for (int i = 0; i < n; ++i) std::cin >> a[i];
    long long x;
    std::cin >> x;

    int left = 0, right = n - 1;
    while (left < right) {
        long long sum = a[left] + a[right];
        if (sum == x) {
            std::cout << "YES\\n";
            return 0;
        }
        if (sum < x) ++left;
        else --right;
    }
    std::cout << "NO\\n";
    return 0;
}
`,
  showcase_sliding_window_min_subarray: `#include <algorithm>
#include <iostream>
#include <vector>

int main() {
    std::ios::sync_with_stdio(false);
    std::cin.tie(nullptr);

    int n;
    std::cin >> n;
    std::vector<long long> a(n);
    for (int i = 0; i < n; ++i) std::cin >> a[i];
    long long target;
    std::cin >> target;

    long long sum = 0;
    int answer = n + 1;
    for (int left = 0, right = 0; right < n; ++right) {
        sum += a[right];
        while (sum >= target) {
            answer = std::min(answer, right - left + 1);
            sum -= a[left++];
        }
    }

    std::cout << (answer == n + 1 ? 0 : answer) << '\\n';
    return 0;
}
`,
  showcase_binary_search_target: `#include <iostream>
#include <vector>

int main() {
    std::ios::sync_with_stdio(false);
    std::cin.tie(nullptr);

    int n;
    std::cin >> n;
    std::vector<long long> a(n);
    for (int i = 0; i < n; ++i) std::cin >> a[i];
    long long x;
    std::cin >> x;

    int low = 0, high = n - 1;
    while (low <= high) {
        int mid = low + (high - low) / 2;
        if (a[mid] == x) {
            std::cout << mid << '\\n';
            return 0;
        }
        if (a[mid] < x) low = mid + 1;
        else high = mid - 1;
    }

    std::cout << -1 << '\\n';
    return 0;
}
`,
  showcase_prefix_sum_range_query: `#include <iostream>
#include <vector>

int main() {
    std::ios::sync_with_stdio(false);
    std::cin.tie(nullptr);

    int n;
    std::cin >> n;
    std::vector<long long> prefix(n + 1, 0);
    for (int i = 1; i <= n; ++i) {
        long long x;
        std::cin >> x;
        prefix[i] = prefix[i - 1] + x;
    }
    int l, r;
    std::cin >> l >> r;

    std::cout << prefix[r] - prefix[l - 1] << '\\n';
    return 0;
}
`,
  showcase_union_find_components: `#include <iostream>
#include <vector>

struct DSU {
    std::vector<int> parent;
    std::vector<int> size;

    explicit DSU(int n) : parent(n + 1), size(n + 1, 1) {
        for (int i = 1; i <= n; ++i) parent[i] = i;
    }

    int find(int x) {
        if (parent[x] == x) return x;
        return parent[x] = find(parent[x]);
    }

    bool unite(int a, int b) {
        a = find(a);
        b = find(b);
        if (a == b) return false;
        if (size[a] < size[b]) std::swap(a, b);
        parent[b] = a;
        size[a] += size[b];
        return true;
    }
};

int main() {
    std::ios::sync_with_stdio(false);
    std::cin.tie(nullptr);

    int n, m;
    std::cin >> n >> m;
    DSU dsu(n);
    int components = n;

    for (int i = 0; i < m; ++i) {
        int u, v;
        std::cin >> u >> v;
        if (dsu.unite(u, v)) --components;
    }

    std::cout << components << '\\n';
    return 0;
}
`,
  showcase_topological_sort_order: `#include <iostream>
#include <queue>
#include <vector>

int main() {
    std::ios::sync_with_stdio(false);
    std::cin.tie(nullptr);

    int n, m;
    std::cin >> n >> m;
    std::vector<std::vector<int>> graph(n + 1);
    std::vector<int> indegree(n + 1, 0);

    for (int i = 0; i < m; ++i) {
        int u, v;
        std::cin >> u >> v;
        graph[u].push_back(v);
        ++indegree[v];
    }

    std::queue<int> q;
    for (int i = 1; i <= n; ++i) {
        if (indegree[i] == 0) q.push(i);
    }

    std::vector<int> order;
    while (!q.empty()) {
        int u = q.front();
        q.pop();
        order.push_back(u);
        for (int v : graph[u]) {
            if (--indegree[v] == 0) q.push(v);
        }
    }

    for (int i = 0; i < static_cast<int>(order.size()); ++i) {
        if (i) std::cout << ' ';
        std::cout << order[i];
    }
    std::cout << '\\n';
    return 0;
}
`,
  showcase_greedy_interval_scheduling: `#include <algorithm>
#include <iostream>
#include <vector>

struct Interval {
    int l;
    int r;
};

int main() {
    std::ios::sync_with_stdio(false);
    std::cin.tie(nullptr);

    int n;
    std::cin >> n;
    std::vector<Interval> intervals(n);
    for (int i = 0; i < n; ++i) std::cin >> intervals[i].l >> intervals[i].r;

    std::sort(intervals.begin(), intervals.end(), [](const Interval& a, const Interval& b) {
        if (a.r != b.r) return a.r < b.r;
        return a.l < b.l;
    });

    int answer = 0;
    int last_end = -2000000000;
    for (const auto& interval : intervals) {
        if (interval.l >= last_end) {
            ++answer;
            last_end = interval.r;
        }
    }

    std::cout << answer << '\\n';
    return 0;
}
`,
  showcase_monotonic_stack_next_greater: `#include <iostream>
#include <stack>
#include <vector>

int main() {
    std::ios::sync_with_stdio(false);
    std::cin.tie(nullptr);

    int n;
    std::cin >> n;
    std::vector<long long> a(n), ans(n, -1);
    for (int i = 0; i < n; ++i) std::cin >> a[i];

    std::stack<int> st;
    for (int i = 0; i < n; ++i) {
        while (!st.empty() && a[st.top()] < a[i]) {
            ans[st.top()] = a[i];
            st.pop();
        }
        st.push(i);
    }

    for (int i = 0; i < n; ++i) {
        if (i) std::cout << ' ';
        std::cout << ans[i];
    }
    std::cout << '\\n';
    return 0;
}
`,
};

export function showcaseReferenceSolution(problem: Record<string, unknown> | null): { code: string; label: string } | null {
  if (!problem) return null;
  const metadata = ((problem._metadata as Record<string, unknown> | undefined) || {});
  const key = String(metadata.question_id || problem.problem_id || '');
  const code = SOLUTIONS[key];
  if (!code) return null;
  return {
    code,
    label: 'showcase reference',
  };
}
