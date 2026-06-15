export interface PersistedRunSession {
  runId: string;
  mode: 'live' | 'replay';
  selectedStageId: string | null;
  selectedTimelineId: string | null;
  replayCursor: number;
  updatedAt: number;
}

const STORAGE_KEY = 'algopilot.dashboard.lastRun';

export function loadPersistedRunSession(storage: Storage): PersistedRunSession | null {
  const raw = storage.getItem(STORAGE_KEY);
  if (!raw) {
    return null;
  }

  try {
    return JSON.parse(raw) as PersistedRunSession;
  } catch {
    storage.removeItem(STORAGE_KEY);
    return null;
  }
}

export function savePersistedRunSession(storage: Storage, value: PersistedRunSession): void {
  storage.setItem(STORAGE_KEY, JSON.stringify(value));
}
