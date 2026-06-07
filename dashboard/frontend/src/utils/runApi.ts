export type FetchLike = typeof fetch;

function normalizeErrorMessage(data: unknown, fallback: string): string {
  if (data && typeof data === 'object') {
    const record = data as Record<string, unknown>;
    const candidates = [record.detail, record.error];
    for (const candidate of candidates) {
      if (typeof candidate === 'string' && candidate.trim()) {
        return candidate;
      }
    }
  }
  return fallback;
}

async function readJsonRecord(response: Response): Promise<Record<string, unknown>> {
  try {
    const data = await response.json() as unknown;
    if (data && typeof data === 'object') {
      return data as Record<string, unknown>;
    }
  } catch {
    // Ignore invalid JSON so callers can fall back to a generic error.
  }
  return {};
}

export async function createRun(
  problem: Record<string, unknown>,
  config: Record<string, unknown>,
  fetchImpl: FetchLike = fetch,
): Promise<{ runId: string; raw: Record<string, unknown> }> {
  const response = await fetchImpl('/api/runs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ problem, config }),
  });

  const data = await readJsonRecord(response);
  if (!response.ok) {
    throw new Error(normalizeErrorMessage(data, 'Dashboard run creation failed'));
  }

  const runId = data.run_id;
  if (typeof runId !== 'string' || runId.trim() === '') {
    throw new Error('Dashboard run creation response is missing run_id');
  }

  return {
    runId,
    raw: data,
  };
}

export async function fetchRunDetail(
  runId: string,
  fetchImpl: FetchLike = fetch,
): Promise<Record<string, unknown>> {
  const response = await fetchImpl(`/api/runs/${runId}`);
  const data = await readJsonRecord(response);

  if (!response.ok) {
    throw new Error(normalizeErrorMessage(data, 'Failed to load run'));
  }

  const returnedRunId = data.run_id;
  if (typeof returnedRunId !== 'string' || returnedRunId.trim() === '') {
    throw new Error(normalizeErrorMessage(data, 'Dashboard run detail response is missing run_id'));
  }

  return data;
}

export async function cancelRun(
  runId: string,
  fetchImpl: FetchLike = fetch,
): Promise<Record<string, unknown>> {
  const response = await fetchImpl(`/api/runs/${runId}/cancel`, { method: 'POST' });
  const data = await readJsonRecord(response);
  if (!response.ok) {
    throw new Error(normalizeErrorMessage(data, 'Failed to interrupt run'));
  }
  return data;
}

export async function deleteRun(
  runId: string,
  fetchImpl: FetchLike = fetch,
): Promise<Record<string, unknown>> {
  const response = await fetchImpl(`/api/runs/${runId}`, { method: 'DELETE' });
  const data = await readJsonRecord(response);
  if (!response.ok) {
    throw new Error(normalizeErrorMessage(data, 'Failed to delete run'));
  }
  return data;
}
