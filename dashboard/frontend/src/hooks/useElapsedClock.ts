import { useEffect, useState } from 'react';

interface UseElapsedClockOptions {
  startAtMs: number | null;
  running: boolean;
}

export function useElapsedClock({ startAtMs, running }: UseElapsedClockOptions): number {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!running || startAtMs === null) {
      return;
    }

    setNow(Date.now());
    const timer = window.setInterval(() => {
      setNow(Date.now());
    }, 1000);

    return () => {
      window.clearInterval(timer);
    };
  }, [running, startAtMs]);

  if (!running || startAtMs === null) {
    return 0;
  }

  return Math.max(0, Math.floor((now - startAtMs) / 1000));
}
