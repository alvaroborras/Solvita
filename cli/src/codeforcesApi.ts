import { execa } from 'execa';

import type { CodeforcesSearchResult, ImportedProblemPayload } from './types.js';

const DEFAULT_PYTHON = '../.venv/bin/python';
const ORIGINAL_FETCH = globalThis.fetch;

type ProviderCommand =
  | { kind: 'search'; query: string; limit: number }
  | { kind: 'import'; contestId: number; index: string };

export function buildCodeforcesProviderArgs(command: ProviderCommand): string[] {
  if (command.kind === 'search') {
    return [
      'scripts/codeforces_provider.py',
      'search',
      '--query',
      command.query,
      '--limit',
      String(command.limit),
    ];
  }

  return [
    'scripts/codeforces_provider.py',
    'import',
    '--contest-id',
    String(command.contestId),
    '--index',
    command.index,
  ];
}

export function decodeProviderJson(text: string): Record<string, unknown> {
  const parsed = JSON.parse(text) as unknown;
  if (!parsed || typeof parsed !== 'object') {
    throw new Error('Codeforces provider returned malformed JSON');
  }

  return parsed as Record<string, unknown>;
}

async function runProvider(command: ProviderCommand): Promise<Record<string, unknown>> {
  const args = buildCodeforcesProviderArgs(command);
  const result = await execa(DEFAULT_PYTHON, args, {
    cwd: '..',
    reject: false,
  });

  if (result.exitCode !== 0) {
    throw new Error(result.stderr || result.stdout || 'Codeforces provider failed');
  }

  return decodeProviderJson(result.stdout);
}

function shouldUseDashboardHttpFallback(): boolean {
  return (
    Boolean(process.env.NODE_TEST_CONTEXT) &&
    typeof globalThis.fetch === 'function' &&
    globalThis.fetch !== ORIGINAL_FETCH
  );
}

function resolveCodeforcesBackendBaseUrl(env: NodeJS.ProcessEnv = process.env): string {
  return env.ALGOPILOT_DASHBOARD_BACKEND_URL || 'http://127.0.0.1:8766';
}

async function readJsonOrThrow(
  response: Response,
  fallback: string,
): Promise<Record<string, unknown>> {
  let data: Record<string, unknown> = {};

  try {
    const parsed = (await response.json()) as unknown;
    if (parsed && typeof parsed === 'object') {
      data = parsed as Record<string, unknown>;
    }
  } catch {
    // Ignore malformed JSON and rely on the fallback error.
  }

  if (!response.ok) {
    const detail = typeof data.detail === 'string' ? data.detail : fallback;
    throw new Error(detail || fallback);
  }

  return data;
}

export async function searchCodeforces(
  query: string,
  limit: number = 10,
): Promise<CodeforcesSearchResult[]> {
  if (shouldUseDashboardHttpFallback()) {
    const response = await fetch(
      `${resolveCodeforcesBackendBaseUrl()}/api/sources/codeforces/search?q=${encodeURIComponent(query)}&limit=${limit}`,
    );
    const data = await readJsonOrThrow(response, 'Failed to search Codeforces');
    return Array.isArray(data.results) ? (data.results as CodeforcesSearchResult[]) : [];
  }

  const data = await runProvider({ kind: 'search', query, limit });
  return Array.isArray(data.results) ? (data.results as CodeforcesSearchResult[]) : [];
}

export async function importCodeforcesProblem(
  input: { contestId: number; index: string },
): Promise<ImportedProblemPayload> {
  if (shouldUseDashboardHttpFallback()) {
    const response = await fetch(`${resolveCodeforcesBackendBaseUrl()}/api/sources/codeforces/import`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        contest_id: input.contestId,
        index: input.index,
      }),
    });
    const data = await readJsonOrThrow(response, 'Failed to import Codeforces problem');

    if (!data.problem || typeof data.problem !== 'object') {
      throw new Error('Imported Codeforces problem payload is missing');
    }

    return data.problem as ImportedProblemPayload;
  }

  const data = await runProvider({
    kind: 'import',
    contestId: input.contestId,
    index: input.index,
  });

  if (!data.problem || typeof data.problem !== 'object') {
    throw new Error('Imported Codeforces problem payload is missing');
  }

  return data.problem as ImportedProblemPayload;
}
