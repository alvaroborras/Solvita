import assert from 'node:assert/strict';
import { delimiter } from 'node:path';
import test from 'node:test';

import {
  buildCodeforcesProviderArgs,
  decodeProviderJson,
  searchCodeforces,
} from './codeforcesApi.ts';

const EXECA_OVERRIDE = Symbol.for('algopilot.codeforcesApi.execa');

type ProviderExecutor = (
  file: string,
  args: string[],
  options: {
    cwd: string;
    reject: false;
    env: NodeJS.ProcessEnv;
  },
) => Promise<{
  exitCode: number | null;
  stdout: string;
  stderr: string;
}>;

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

test('searchCodeforces runs the provider subprocess and returns parsed results', async () => {
  let call:
    | {
        file: string;
        args: string[];
        options: {
          cwd: string;
          reject: false;
          env: NodeJS.ProcessEnv;
        };
      }
    | null = null;

  const globalWithOverride = globalThis as typeof globalThis & {
    [EXECA_OVERRIDE]?: ProviderExecutor;
  };

  globalWithOverride[EXECA_OVERRIDE] = async (file, args, options) => {
    call = { file, args, options };

    return {
      exitCode: 0,
      stdout: JSON.stringify({
        results: [
          {
            contest_id: 1575,
            index: 'C',
            name: 'Cyclic Sum',
            tags: ['data structures'],
            url: 'https://codeforces.com/contest/1575/problem/C',
            problem_id: 'codeforces_1575_C',
          },
        ],
      }),
      stderr: '',
    };
  };

  try {
    assert.deepEqual(await searchCodeforces('1575 C', 10), [
      {
        contest_id: 1575,
        index: 'C',
        name: 'Cyclic Sum',
        tags: ['data structures'],
        url: 'https://codeforces.com/contest/1575/problem/C',
        problem_id: 'codeforces_1575_C',
      },
    ]);

    assert.equal(call?.file, '../.venv/bin/python');
    assert.deepEqual(call?.args, [
      'scripts/codeforces_provider.py',
      'search',
      '--query',
      '1575 C',
      '--limit',
      '10',
    ]);
    assert.equal(call?.options.cwd, '..');
    assert.equal(call?.options.reject, false);
    assert.ok(call?.options.env.PYTHONPATH?.split(delimiter).includes('.'));
  } finally {
    delete globalWithOverride[EXECA_OVERRIDE];
  }
});
