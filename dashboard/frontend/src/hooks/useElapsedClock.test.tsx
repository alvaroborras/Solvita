import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { useElapsedClock } from './useElapsedClock';

describe('useElapsedClock', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('keeps elapsed seconds moving even when no new token event arrives', () => {
    vi.useFakeTimers();
    vi.setSystemTime(1000);

    const { result } = renderHook(() => useElapsedClock({ startAtMs: 1000, running: true }));

    expect(result.current).toBe(0);

    act(() => {
      vi.setSystemTime(6000);
      vi.advanceTimersByTime(1000);
    });

    expect(result.current).toBe(6);
  });

  it('returns zero when the clock is idle or has no start timestamp', () => {
    vi.useFakeTimers();
    vi.setSystemTime(4000);

    const { result, rerender } = renderHook(
      ({ startAtMs, running }) => useElapsedClock({ startAtMs, running }),
      {
        initialProps: {
          startAtMs: 1000 as number | null,
          running: false,
        },
      },
    );

    expect(result.current).toBe(0);

    rerender({ startAtMs: null, running: true });

    expect(result.current).toBe(0);
  });
});
