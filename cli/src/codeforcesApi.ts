import type { CodeforcesSearchResult, ImportedProblemPayload } from './types.js';

export function resolveCodeforcesBackendBaseUrl(
  env: NodeJS.ProcessEnv = process.env,
): string {
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
  env: NodeJS.ProcessEnv = process.env,
): Promise<CodeforcesSearchResult[]> {
  const baseUrl = resolveCodeforcesBackendBaseUrl(env);
  const response = await fetch(
    `${baseUrl}/api/sources/codeforces/search?q=${encodeURIComponent(query)}&limit=${limit}`,
  );
  const data = await readJsonOrThrow(response, 'Failed to search Codeforces');

  return Array.isArray(data.results) ? (data.results as CodeforcesSearchResult[]) : [];
}

export async function importCodeforcesProblem(
  input: { contestId: number; index: string },
  env: NodeJS.ProcessEnv = process.env,
): Promise<ImportedProblemPayload> {
  const baseUrl = resolveCodeforcesBackendBaseUrl(env);
  const response = await fetch(`${baseUrl}/api/sources/codeforces/import`, {
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
