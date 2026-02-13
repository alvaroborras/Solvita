## Skill: QuickSort_InPlace
- Tag: Quick_Sort
- Category: sorting
- Applicable_when: in-place sorting, not stable, typical CP constraints
- Not_for: requires stability; strict worst-case O(n log n)
- Complexity: avg O(n log n), worst O(n^2), space O(log n) expected
- Pitfalls: recursion depth; duplicates; RNG seeding/reproducibility

### Snippet (C++17)

```cpp
#include <vector>
#include <algorithm>
#include <random>
#include <utility>

using namespace std;

inline void insertion_sort(vector<int>& a, int l, int r) {
    for (int i = l + 1; i <= r; ++i) {
        int key = a[i], j = i - 1;
        while (j >= l && a[j] > key) {
            a[j + 1] = a[j];
            --j;
        }
        a[j + 1] = key;
    }
}

void quick_sort(vector<int>& a, int l, int r, mt19937& rng) {
    if (l >= r) return;

    // Small-range optimization
    if (r - l + 1 <= 16) {
        insertion_sort(a, l, r);
        return;
    }

    // Randomized pivot to reduce adversarial worst-case risk
    uniform_int_distribution<int> dist(l, r);
    int pivot_idx = dist(rng);
    int x = a[pivot_idx];

    int i = l - 1, j = r + 1;
    while (i < j) {
        do ++i; while (a[i] < x);
        do --j; while (a[j] > x);
        if (i < j) swap(a[i], a[j]);
    }

    // Recursively sort [l, j] and [j + 1, r]
    quick_sort(a, l, j, rng);
    quick_sort(a, j + 1, r, rng);
}

// Usage example:
// mt19937 rng(seed);
// quick_sort(arr, 0, n - 1, rng);
```
