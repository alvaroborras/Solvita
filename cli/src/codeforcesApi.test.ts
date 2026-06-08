import assert from 'node:assert/strict';
import test from 'node:test';

import {
  importCodeforcesProblem,
  resolveCodeforcesBackendBaseUrl,
  searchCodeforces,
} from './codeforcesApi.ts';

test('resolveCodeforcesBackendBaseUrl prefers ALGOPILOT_DASHBOARD_BACKEND_URL', () => {
  assert.equal(
    resolveCodeforcesBackendBaseUrl({
      ALGOPILOT_DASHBOARD_BACKEND_URL: 'http://127.0.0.1:9999',
    }),
    'http://127.0.0.1:9999',
  );
});

test('resolveCodeforcesBackendBaseUrl falls back to http://127.0.0.1:8766', () => {
  assert.equal(resolveCodeforcesBackendBaseUrl({}), 'http://127.0.0.1:8766');
});

test('searchCodeforces parses a successful search response and returns codeforces_1575_C', async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (url: string | URL) => {
    assert.equal(
      url.toString(),
      'http://127.0.0.1:8766/api/sources/codeforces/search?q=1575%20C&limit=10',
    );

    return {
      ok: true,
      json: async () => ({
        results: [
          {
            contest_id: 1575,
            index: 'C',
            name: 'Cyclic Sum',
            rating: 2100,
            tags: ['math', 'dp'],
            url: 'https://codeforces.com/contest/1575/problem/C',
            problem_id: 'codeforces_1575_C',
          },
        ],
        cache_status: 'ready',
      }),
    };
  }) as typeof fetch;

  try {
    const rows = await searchCodeforces('1575 C', 10, {
      ALGOPILOT_DASHBOARD_BACKEND_URL: 'http://127.0.0.1:8766',
    });

    assert.equal(rows.length, 1);
    assert.equal(rows[0]?.problem_id, 'codeforces_1575_C');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('importCodeforcesProblem posts to /api/sources/codeforces/import and returns imported payload with _metadata.source = codeforces', async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (url: string | URL, init?: RequestInit) => {
    assert.equal(url.toString(), 'http://127.0.0.1:8766/api/sources/codeforces/import');
    assert.equal(init?.method, 'POST');
    assert.deepEqual(JSON.parse(String(init?.body)), {
      contest_id: 1575,
      index: 'C',
    });

    return {
      ok: true,
      json: async () => ({
        problem_id: 'codeforces_1575_C',
        filename: 'codeforces_1575_C.json',
        problem: {
          problem_id: 'codeforces_1575_C',
          description: 'Imported Codeforces problem',
          public_tests: [],
          _metadata: { source: 'codeforces', name: 'Cyclic Sum' },
        },
      }),
    };
  }) as typeof fetch;

  try {
    const problem = await importCodeforcesProblem(
      { contestId: 1575, index: 'C' },
      { ALGOPILOT_DASHBOARD_BACKEND_URL: 'http://127.0.0.1:8766' },
    );

    assert.equal(problem.problem_id, 'codeforces_1575_C');
    assert.equal((problem._metadata as Record<string, unknown>)?.source, 'codeforces');
  } finally {
    globalThis.fetch = originalFetch;
  }
});
