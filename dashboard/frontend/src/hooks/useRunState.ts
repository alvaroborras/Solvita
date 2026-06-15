import { useReducer, useCallback, useMemo } from 'react';
import { AlgoPilotEvent } from '../types/events';
import { DagDefinition } from '../types/dag';
import { createDagReducer, initialDagState } from '../state/dagReducer';
import { useWebSocket } from './useWebSocket';

export function useRunState(runId: string | null, definition: DagDefinition | null) {
  const dagReducerFn = useMemo(() => createDagReducer(definition), [definition]);
  const [dagState, dispatchDag] = useReducer(dagReducerFn, initialDagState);

  const handleEvent = useCallback((event: AlgoPilotEvent) => {
    dispatchDag(event);
  }, []);

  const { status } = useWebSocket({ runId, onEvent: handleEvent });

  const reset = useCallback(() => {
    dispatchDag({ type: 'solve_start', ts: 0, seq: 0, problem_name: '' });
  }, []);

  return { dagState, wsStatus: status, handleEvent, reset };
}
