import { useCallback, useEffect, useRef, useState } from 'react';

import type { RunDetailState, RunSessionState } from '../state/runSessionReducer';
import { createInitialRunSessionState } from '../state/runSessionReducer';
import type { AlgoPilotEvent } from '../types/events';
import { mergeRunEvents } from '../utils/mergeRunEvents';
import type { PersistedRunSession } from '../utils/persistedRunSession';
import { loadPersistedRunSession, savePersistedRunSession } from '../utils/persistedRunSession';
import type { FetchLike } from '../utils/runApi';
import { fetchRunDetail } from '../utils/runApi';
import { useWebSocket } from './useWebSocket';

const PERSISTED_RUN_SESSION_KEY = 'algopilot.dashboard.lastRun';

interface UseRunSessionOptions {
  fetchImpl?: FetchLike;
  storage?: Storage;
}

interface HydrateOptions {
  mergeExisting?: boolean;
  persisted?: PersistedRunSession | null;
  preserveSessionOnFailure?: boolean;
  reconnecting?: boolean;
}

interface HydratedRun {
  active: boolean;
  requestedMode: 'live' | 'replay';
}

type SessionUpdater = RunSessionState | ((current: RunSessionState) => RunSessionState);

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object';
}

function normalizeNumber(value: unknown, fallback: number): number {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === 'string') {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return fallback;
}

function normalizeEvent(raw: unknown, index: number): AlgoPilotEvent | null {
  if (!isRecord(raw)) {
    return null;
  }

  const envelope = raw.event;
  const payload = isRecord(envelope) ? envelope : raw;
  if (typeof payload.type !== 'string') {
    return null;
  }

  const seq = normalizeNumber(raw.seq, index);
  const ts = normalizeNumber(raw.timestamp ?? raw.ts ?? payload.ts, seq);
  return {
    ...payload,
    seq,
    ts,
  } as AlgoPilotEvent;
}

function normalizeEvents(rawEvents: unknown): AlgoPilotEvent[] {
  if (!Array.isArray(rawEvents)) {
    return [];
  }

  const normalized = rawEvents
    .map((entry, index) => normalizeEvent(entry, index))
    .filter((event): event is AlgoPilotEvent => event !== null);

  return mergeRunEvents([], normalized);
}

function eventFinalStatus(event: AlgoPilotEvent): string | null {
  const record = event as Record<string, unknown>;
  const candidates = [record.final_status, record.status];
  for (const candidate of candidates) {
    if (typeof candidate === 'string' && candidate.trim()) {
      return candidate;
    }
  }
  return null;
}

function deriveFinalStatus(raw: Record<string, unknown>, events: AlgoPilotEvent[]): string | null {
  if (typeof raw.final_status === 'string' && raw.final_status.trim()) {
    return raw.final_status;
  }

  for (let index = events.length - 1; index >= 0; index -= 1) {
    const status = eventFinalStatus(events[index]);
    if (status) {
      return status;
    }
  }

  return null;
}

function normalizeRunDetailPayload(
  runId: string,
  raw: Record<string, unknown>,
): { events: AlgoPilotEvent[]; finalStatus: string | null; runDetail: RunDetailState } {
  const events = normalizeEvents(raw.events);
  const finalStatus = deriveFinalStatus(raw, events);

  return {
    events,
    finalStatus,
    runDetail: {
      runId: typeof raw.run_id === 'string' && raw.run_id.trim() ? raw.run_id : runId,
      problemId: typeof raw.problem_id === 'string' && raw.problem_id.trim() ? raw.problem_id : 'unknown',
      problem: isRecord(raw.problem) ? raw.problem : {},
      config: isRecord(raw.config) ? raw.config : {},
      finalStatus,
    },
  };
}

function classifyHydrationFailure(error: unknown): RunSessionState['hydrationStatus'] {
  const message = error instanceof Error ? error.message.toLowerCase() : '';
  if (message.includes('not found') || message.includes('missing run_id')) {
    return 'missing';
  }
  return 'error';
}

function selectionStateFor(
  current: RunSessionState,
  runId: string,
  persisted?: PersistedRunSession | null,
): Pick<RunSessionState, 'replayCursor' | 'selectedStageId' | 'selectedTimelineId'> & {
  source: 'persisted' | 'current' | 'default';
  persistedMode: PersistedRunSession['mode'] | null;
} {
  if (persisted) {
    return {
      source: 'persisted',
      persistedMode: persisted.mode,
      selectedStageId: persisted.selectedStageId,
      selectedTimelineId: persisted.selectedTimelineId,
      replayCursor: persisted.replayCursor,
    };
  }

  if (current.runId === runId) {
    return {
      source: 'current',
      persistedMode: null,
      selectedStageId: current.selectedStageId,
      selectedTimelineId: current.selectedTimelineId,
      replayCursor: current.replayCursor,
    };
  }

  return {
    source: 'default',
    persistedMode: null,
    selectedStageId: null,
    selectedTimelineId: null,
    replayCursor: 0,
  };
}

function clearPersistedRunSession(storage: Storage): void {
  storage.removeItem(PERSISTED_RUN_SESSION_KEY);
}

export function useRunSession({
  fetchImpl = fetch,
  storage = window.localStorage,
}: UseRunSessionOptions = {}) {
  const [session, setSession] = useState<RunSessionState>(() => createInitialRunSessionState());
  const [socketEnabled, setSocketEnabledState] = useState(false);
  const hydrateGenerationRef = useRef(0);
  const reconnectInFlightRef = useRef(false);
  const restoreAttemptedRef = useRef(false);
  const sessionRef = useRef(session);

  const setSessionState = useCallback((updater: SessionUpdater) => {
    setSession((current) => {
      const next = typeof updater === 'function'
        ? (updater as (value: RunSessionState) => RunSessionState)(current)
        : updater;
      sessionRef.current = next;
      return next;
    });
  }, []);

  const setSocketEnabled = useCallback((enabled: boolean) => {
    setSocketEnabledState(enabled);
  }, []);

  const hydrateRun = useCallback(async (
    runId: string,
    requestedMode: 'live' | 'replay',
    options: HydrateOptions = {},
  ): Promise<HydratedRun | null> => {
    const hydrateGeneration = hydrateGenerationRef.current + 1;
    hydrateGenerationRef.current = hydrateGeneration;
    const persisted = options.persisted ?? null;
    const previousSession = sessionRef.current;
    const isStaleHydration = () => hydrateGenerationRef.current !== hydrateGeneration;
    const initialSelection = selectionStateFor(previousSession, runId, persisted);

    setSocketEnabled(false);
    setSessionState((current) => {
      const keepCurrent = current.runId === runId || options.preserveSessionOnFailure;
      const base = keepCurrent ? current : createInitialRunSessionState();
      return {
        ...base,
        runId,
        mode: requestedMode,
        hydrationStatus: 'restoring',
        shouldConnectLive: false,
        wsStatus: options.reconnecting
          ? 'reconnecting'
          : requestedMode === 'live'
            ? 'connecting'
            : 'disconnected',
        ...initialSelection,
      };
    });

    try {
      const raw = await fetchRunDetail(runId, fetchImpl);
      if (isStaleHydration()) {
        return null;
      }

      const normalized = normalizeRunDetailPayload(runId, raw);
      const current = sessionRef.current;
      const sameRun = current.runId === runId;
      const events = sameRun || options.mergeExisting
        ? mergeRunEvents(current.events, normalized.events)
        : normalized.events;
      const finalStatus = deriveFinalStatus(
        { ...raw, final_status: normalized.finalStatus },
        events,
      );
      const mode = finalStatus ? 'replay' : requestedMode;
      const active = mode === 'live' && finalStatus === null;
      const resolvedSelection = initialSelection;
      const replayCursor = mode !== 'replay'
        ? resolvedSelection.replayCursor
        : resolvedSelection.source === 'current'
          ? resolvedSelection.replayCursor
          : resolvedSelection.source === 'persisted' && resolvedSelection.persistedMode === 'replay'
            ? resolvedSelection.replayCursor
            : events.length;

      setSessionState({
        ...current,
        runId: normalized.runDetail.runId,
        mode,
        hydrationStatus: 'ready',
        runDetail: {
          ...normalized.runDetail,
          finalStatus,
        },
        events,
        shouldConnectLive: active,
        wsStatus: active
          ? (options.reconnecting ? 'reconnecting' : 'connecting')
          : 'disconnected',
        ...resolvedSelection,
        replayCursor,
      });

      if (active) {
        setSocketEnabled(true);
      }

      return {
        active,
        requestedMode,
      };
    } catch (error) {
      if (isStaleHydration()) {
        return null;
      }

      const hydrationStatus = classifyHydrationFailure(error);
      if (persisted) {
        clearPersistedRunSession(storage);
      }

      setSessionState(() => {
        if (options.preserveSessionOnFailure) {
          return {
            ...previousSession,
            hydrationStatus,
            shouldConnectLive: false,
            wsStatus: 'error',
          };
        }

        return {
          ...createInitialRunSessionState(),
          hydrationStatus,
        };
      });

      return null;
    }
  }, [fetchImpl, setSessionState, setSocketEnabled, storage]);

  const reconnect = useCallback(async () => {
    const current = sessionRef.current;
    if (!current.runId || current.mode !== 'live' || reconnectInFlightRef.current) {
      return false;
    }

    reconnectInFlightRef.current = true;
    setSocketEnabled(false);
    setSessionState((value) => ({
      ...value,
      wsStatus: 'reconnecting',
    }));

    try {
      const hydrated = await hydrateRun(current.runId, 'live', {
        mergeExisting: true,
        preserveSessionOnFailure: true,
        reconnecting: true,
      });
      return Boolean(hydrated);
    } finally {
      reconnectInFlightRef.current = false;
    }
  }, [hydrateRun, setSessionState, setSocketEnabled]);

  const handleSocketEvent = useCallback((event: AlgoPilotEvent) => {
    const current = sessionRef.current;
    const events = mergeRunEvents(current.events, [event]);
    const finalStatus = eventFinalStatus(event) ?? current.runDetail?.finalStatus ?? null;
    const completed = current.mode === 'live' && finalStatus !== null;

    setSessionState({
      ...current,
      mode: completed ? 'replay' : current.mode,
      runDetail: current.runDetail
        ? {
            ...current.runDetail,
            finalStatus,
          }
        : current.runDetail,
      events,
      shouldConnectLive: completed ? false : current.shouldConnectLive,
      wsStatus: completed ? 'disconnected' : current.wsStatus,
    });

    if (completed) {
      setSocketEnabled(false);
    }
  }, [setSessionState, setSocketEnabled]);

  const handleSocketOpen = useCallback(() => {
    setSessionState((current) => ({
      ...current,
      wsStatus: 'connected',
    }));
  }, [setSessionState]);

  const handleSocketFailure = useCallback(() => {
    const current = sessionRef.current;
    if (!current.runId || current.mode !== 'live' || !current.shouldConnectLive) {
      return;
    }
    void reconnect();
  }, [reconnect]);

  useWebSocket({
    runId: session.runId,
    enabled: socketEnabled && session.shouldConnectLive,
    onClose: handleSocketFailure,
    onError: handleSocketFailure,
    onEvent: handleSocketEvent,
    onOpen: handleSocketOpen,
  });

  const selectLiveRun = useCallback((runId: string) => (
    hydrateRun(runId, 'live', {
      preserveSessionOnFailure: sessionRef.current.runId === runId,
    }).then(Boolean)
  ), [hydrateRun]);

  const selectReplayRun = useCallback((runId: string) => (
    hydrateRun(runId, 'replay').then(Boolean)
  ), [hydrateRun]);

  const restoreLatestRun = useCallback(async () => {
    const persisted = loadPersistedRunSession(storage);
    if (!persisted) {
      return false;
    }

    const restored = await hydrateRun(persisted.runId, persisted.mode, {
      persisted,
    });
    return Boolean(restored);
  }, [hydrateRun, storage]);

  const clearSession = useCallback(() => {
    hydrateGenerationRef.current += 1;
    clearPersistedRunSession(storage);
    setSocketEnabled(false);
    setSessionState(createInitialRunSessionState());
  }, [setSessionState, setSocketEnabled, storage]);

  const dropRun = useCallback((runId: string) => {
    const current = sessionRef.current;
    if (current.runId !== runId) {
      return;
    }
    hydrateGenerationRef.current += 1;
    clearPersistedRunSession(storage);
    setSocketEnabled(false);
    setSessionState(createInitialRunSessionState());
  }, [setSessionState, setSocketEnabled, storage]);

  const setSelectedStageId = useCallback((selectedStageId: string | null) => {
    setSessionState((current) => ({
      ...current,
      selectedStageId,
    }));
  }, [setSessionState]);

  const setSelectedTimelineId = useCallback((selectedTimelineId: string | null) => {
    setSessionState((current) => ({
      ...current,
      selectedTimelineId,
    }));
  }, [setSessionState]);

  const setReplayCursor = useCallback((replayCursor: number) => {
    setSessionState((current) => ({
      ...current,
      replayCursor,
    }));
  }, [setSessionState]);

  useEffect(() => {
    sessionRef.current = session;
  }, [session]);

  useEffect(() => {
    if (restoreAttemptedRef.current) {
      return;
    }
    restoreAttemptedRef.current = true;
    void restoreLatestRun();
  }, [restoreLatestRun]);

  useEffect(() => {
    if (session.hydrationStatus !== 'ready' || !session.runId || session.mode === 'idle') {
      return;
    }

    savePersistedRunSession(storage, {
      runId: session.runId,
      mode: session.mode === 'replay' ? 'replay' : 'live',
      selectedStageId: session.selectedStageId,
      selectedTimelineId: session.selectedTimelineId,
      replayCursor: session.replayCursor,
      updatedAt: Date.now(),
    });
  }, [
    session.hydrationStatus,
    session.mode,
    session.replayCursor,
    session.runId,
    session.selectedStageId,
    session.selectedTimelineId,
    storage,
  ]);

  return {
    clearSession,
    dropRun,
    reconnect,
    restoreLatestRun,
    selectLiveRun,
    selectReplayRun,
    session,
    setReplayCursor,
    setSelectedStageId,
    setSelectedTimelineId,
  };
}
