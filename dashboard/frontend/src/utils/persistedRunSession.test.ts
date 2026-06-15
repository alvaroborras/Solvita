import { describe, expect, it, vi } from 'vitest';

import { loadPersistedRunSession, savePersistedRunSession } from './persistedRunSession';

describe('persistedRunSession', () => {
  it('round-trips the last viewed run', () => {
    const storage = window.localStorage;
    storage.clear();

    savePersistedRunSession(storage, {
      runId: 'run-123',
      mode: 'live',
      selectedStageId: 'verify',
      selectedTimelineId: 'verify-1',
      replayCursor: 0,
      updatedAt: 1234,
    });

    expect(loadPersistedRunSession(storage)).toEqual({
      runId: 'run-123',
      mode: 'live',
      selectedStageId: 'verify',
      selectedTimelineId: 'verify-1',
      replayCursor: 0,
      updatedAt: 1234,
    });
  });

  it('clears malformed persisted data', () => {
    const storage: Storage = {
      length: 1,
      clear: () => undefined,
      key: () => null,
      getItem: () => '{not-json',
      removeItem: () => undefined,
      setItem: () => undefined,
    };
    const removeItem = vi.spyOn(storage, 'removeItem');

    expect(loadPersistedRunSession(storage)).toBeNull();
    expect(removeItem).toHaveBeenCalledOnce();
  });
});
