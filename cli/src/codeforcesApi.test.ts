import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildCodeforcesProviderArgs,
  decodeProviderJson,
} from './codeforcesApi.ts';

test('buildCodeforcesProviderArgs builds search arguments for 1575 C', () => {
  assert.deepEqual(
    buildCodeforcesProviderArgs({
      kind: 'search',
      query: '1575 C',
      limit: 10,
    }),
    ['scripts/codeforces_provider.py', 'search', '--query', '1575 C', '--limit', '10'],
  );
});

test('buildCodeforcesProviderArgs builds import arguments for contest 1575 problem C', () => {
  assert.deepEqual(
    buildCodeforcesProviderArgs({
      kind: 'import',
      contestId: 1575,
      index: 'C',
    }),
    ['scripts/codeforces_provider.py', 'import', '--contest-id', '1575', '--index', 'C'],
  );
});

test('decodeProviderJson parses JSON text to an object', () => {
  assert.deepEqual(
    decodeProviderJson('{"results":[{"problem_id":"codeforces_1575_C"}]}'),
    {
      results: [{ problem_id: 'codeforces_1575_C' }],
    },
  );
});
