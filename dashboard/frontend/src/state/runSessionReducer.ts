import type { AlgoPilotEvent } from '../types/events';

export interface RunDetailState {
  runId: string;
  problemId: string;
  problem: Record<string, unknown>;
  config: Record<string, unknown>;
  finalStatus?: string | null;
}

export interface RunSessionState {
  runId: string | null;
  mode: 'idle' | 'live' | 'replay';
  hydrationStatus: 'idle' | 'restoring' | 'ready' | 'missing' | 'error';
  wsStatus: 'disconnected' | 'connecting' | 'connected' | 'reconnecting' | 'error';
  runDetail: RunDetailState | null;
  events: AlgoPilotEvent[];
  shouldConnectLive: boolean;
  selectedStageId: string | null;
  selectedTimelineId: string | null;
  replayCursor: number;
}

export interface HydrateSucceededAction {
  type: 'hydrate_succeeded';
  runDetail: RunDetailState;
  events: AlgoPilotEvent[];
  mode: 'live' | 'replay';
  shouldConnectLive: boolean;
}

export type RunSessionAction = HydrateSucceededAction;

export function createInitialRunSessionState(): RunSessionState {
  return {
    runId: null,
    mode: 'idle',
    hydrationStatus: 'idle',
    wsStatus: 'disconnected',
    runDetail: null,
    events: [],
    shouldConnectLive: false,
    selectedStageId: null,
    selectedTimelineId: null,
    replayCursor: 0,
  };
}

export function reduceRunSession(state: RunSessionState, action: RunSessionAction): RunSessionState {
  switch (action.type) {
    case 'hydrate_succeeded':
      return {
        ...state,
        runId: action.runDetail.runId,
        mode: action.mode,
        hydrationStatus: 'ready',
        runDetail: action.runDetail,
        events: action.events,
        shouldConnectLive: action.shouldConnectLive,
      };
    default:
      return state;
  }
}
