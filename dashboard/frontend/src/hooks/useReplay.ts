import { useState, useRef, useCallback, useEffect } from 'react';
import { AlgoPilotEvent } from '../types/events';

interface ReplayState {
  events: AlgoPilotEvent[];
  cursor: number;
  playing: boolean;
  speed: number;
}

export function useReplay(onEvent: (event: AlgoPilotEvent) => void, reset: () => void) {
  const [state, setState] = useState<ReplayState>({
    events: [],
    cursor: 0,
    playing: false,
    speed: 1,
  });
  const timerRef = useRef<number | null>(null);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  const load = useCallback((events: AlgoPilotEvent[], cursor = 0) => {
    reset();
    const clampedCursor = Math.max(0, Math.min(cursor, events.length));
    for (let i = 0; i < clampedCursor; i++) {
      onEventRef.current(events[i]);
    }
    setState({ events, cursor: clampedCursor, playing: false, speed: 1 });
  }, [reset]);

  const replayTo = useCallback((targetCursor: number) => {
    setState((prev) => {
      reset();
      const clamped = Math.max(0, Math.min(targetCursor, prev.events.length));
      for (let i = 0; i < clamped; i++) {
        onEventRef.current(prev.events[i]);
      }
      return { ...prev, cursor: clamped };
    });
  }, [reset]);

  const step = useCallback((dir: 1 | -1) => {
    setState((prev) => {
      const next = prev.cursor + dir;
      if (next < 0 || next > prev.events.length) return prev;
      if (dir === 1) {
        onEventRef.current(prev.events[prev.cursor]);
      } else {
        reset();
        for (let i = 0; i < next; i++) {
          onEventRef.current(prev.events[i]);
        }
      }
      return { ...prev, cursor: next };
    });
  }, [reset]);

  const play = useCallback(() => setState((s) => ({ ...s, playing: true })), []);
  const pause = useCallback(() => setState((s) => ({ ...s, playing: false })), []);
  const setSpeed = useCallback((speed: number) => setState((s) => ({ ...s, speed })), []);

  useEffect(() => {
    if (!state.playing || state.cursor >= state.events.length) {
      if (timerRef.current) clearTimeout(timerRef.current);
      if (state.playing && state.cursor >= state.events.length) {
        setState((s) => ({ ...s, playing: false }));
      }
      return;
    }

    const current = state.events[state.cursor];
    const next = state.events[state.cursor + 1];
    let delay = 200;
    if (next) {
      delay = Math.min(2000, Math.max(50, (next.ts - current.ts) * 1000));
    }
    delay /= state.speed;

    timerRef.current = window.setTimeout(() => {
      step(1);
    }, delay);

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [state.playing, state.cursor, state.speed, state.events, step]);

  return {
    ...state,
    total: state.events.length,
    load,
    play,
    pause,
    step,
    replayTo,
    setSpeed,
  };
}
