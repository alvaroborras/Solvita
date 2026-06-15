import type { FinalArtifactSnapshot } from '../types/artifacts';
import type { AlgoPilotEvent } from '../types/events';
import type { JourneyStageId } from '../types/journey';
import { STAGE_META, nodeLabel, nodeSummary, nodeToStageId, phaseToStageId } from './buildSolveJourney';

interface LiveProgressMetrics {
  iteration: number | null;
  passed: number | null;
  total: number | null;
  resultStatus: string | null;
  hackRound: number | null;
}

export interface LiveProgress {
  stageId: JourneyStageId | null;
  currentStepLabel: string;
  currentStepSummary: string;
  metrics: LiveProgressMetrics;
}

interface StagePointer {
  stageId: JourneyStageId | null;
  event: AlgoPilotEvent | null;
}

function eventSeq(event: AlgoPilotEvent | null): number {
  return event?.seq ?? Number.NEGATIVE_INFINITY;
}

function normalizeString(value: unknown): string | null {
  if (typeof value !== 'string') {
    return null;
  }
  const normalized = value.trim();
  return normalized.length > 0 ? normalized : null;
}

function normalizeNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function phaseDoneData(event: AlgoPilotEvent | null): Record<string, unknown> {
  if (!event || event.type !== 'phase_done') {
    return {};
  }
  const raw = (event as { data?: Record<string, unknown> }).data;
  return raw && typeof raw === 'object' ? raw : {};
}

function findLastStagePointer(events: AlgoPilotEvent[]): StagePointer {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];
    if (event.type === 'node_enter') {
      const stageId = nodeToStageId((event as { node_id?: string }).node_id);
      if (stageId) {
        return { stageId, event };
      }
      continue;
    }

    if (event.type === 'phase_start' || event.type === 'phase_done') {
      const stageId = phaseToStageId((event as { phase?: string }).phase);
      if (stageId) {
        return { stageId, event };
      }
      continue;
    }

    if (event.type === 'solve_start') {
      return { stageId: 'read_problem', event };
    }
  }

  return { stageId: null, event: null };
}

function findLastPhaseDone(events: AlgoPilotEvent[], phase: string): AlgoPilotEvent | null {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];
    if (event.type === 'phase_done' && (event as { phase?: string }).phase === phase) {
      return event;
    }
  }
  return null;
}

function findLastFinalEvent(events: AlgoPilotEvent[]): AlgoPilotEvent | null {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    if (events[index].type === 'final') {
      return events[index];
    }
  }
  return null;
}

function findLastArtifactSnapshot(events: AlgoPilotEvent[]): AlgoPilotEvent | null {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    if (events[index].type === 'artifact_snapshot') {
      return events[index];
    }
  }
  return null;
}

function stageTitle(stageId: JourneyStageId | null): string | null {
  if (!stageId) {
    return null;
  }
  return STAGE_META.find((stage) => stage.id === stageId)?.title ?? null;
}

function phaseSummary(stageId: JourneyStageId | null, event: AlgoPilotEvent | null): string | null {
  if (!stageId || !event) {
    return null;
  }

  if (event.type === 'node_enter') {
    return nodeSummary((event as { node_id?: string }).node_id || '');
  }

  if (event.type === 'phase_start') {
    return STAGE_META.find((stage) => stage.id === stageId)?.shortDescription ?? null;
  }

  if (event.type !== 'phase_done') {
    return null;
  }

  const data = phaseDoneData(event);
  if (stageId === 'codegen') {
    const passed = normalizeNumber(data.passed);
    const total = normalizeNumber(data.total);
    if (passed !== null && total !== null) {
      return `Latest visible score: ${passed}/${total}.`;
    }
  }


  if (stageId === 'hack') {
    const round = normalizeNumber(data.hack_round);
    if (round !== null) {
      return `Hack round ${round} completed.`;
    }
  }

  return STAGE_META.find((stage) => stage.id === stageId)?.shortDescription ?? null;
}

function pickMetric<T>(...values: Array<T | null | undefined>): T | null {
  for (const value of values) {
    if (value !== null && value !== undefined) {
      return value;
    }
  }
  return null;
}

function latestExecutionLine(artifact: FinalArtifactSnapshot | null): string | null {
  const lastLine = artifact?.executionLogTail[artifact.executionLogTail.length - 1];
  return normalizeString(lastLine);
}

export function buildLiveProgress({
  events,
  artifact,
}: {
  events: AlgoPilotEvent[];
  artifact: FinalArtifactSnapshot | null;
}): LiveProgress {
  const { stageId, event: stageEvent } = findLastStagePointer(events);
  const lastArtifactEvent = findLastArtifactSnapshot(events);
  const lastCodegen = findLastPhaseDone(events, 'codegen_phase');
  const lastHack = findLastPhaseDone(events, 'hacker_phase');
  const finalEvent = findLastFinalEvent(events);
  const codegenData = phaseDoneData(lastCodegen);
  const hackData = phaseDoneData(lastHack);
  const finalRecord = (finalEvent || {}) as Record<string, unknown>;
  const stepSummary = phaseSummary(stageId, stageEvent);
  const executionLine = latestExecutionLine(artifact);
  const executionLineIsCurrent = executionLine !== null && eventSeq(lastArtifactEvent) >= eventSeq(stageEvent);

  const labelFromEvent = stageEvent?.type === 'node_enter'
    ? nodeLabel((stageEvent as { node_id?: string }).node_id || '')
    : normalizeString((stageEvent as { label?: string } | null)?.label)
      ?? stageTitle(stageId);

  return {
    stageId,
    currentStepLabel: labelFromEvent ?? (finalEvent ? 'Run complete' : 'Waiting for next event'),
    currentStepSummary: executionLineIsCurrent
      ? executionLine
      : stepSummary
        ?? executionLine
      ?? stepSummary
      ?? normalizeString(finalRecord.status)
      ?? 'Preparing progress view.',
    metrics: {
      iteration: pickMetric(
        artifact?.iteration,
        normalizeNumber(codegenData.iteration),
        normalizeNumber(finalRecord.iterations),
      ),
      passed: pickMetric(
        artifact?.tests.passedTests,
        normalizeNumber(codegenData.passed),
        normalizeNumber(finalRecord.passed),
      ),
      total: pickMetric(
        artifact?.tests.totalTests,
        normalizeNumber(codegenData.total),
        normalizeNumber(finalRecord.total),
      ),
      resultStatus: pickMetric(
        normalizeString(artifact?.status),
        normalizeString(finalRecord.status),
      ),
      hackRound: pickMetric(
        artifact?.hack.round,
        normalizeNumber(hackData.hack_round),
      ),
    },
  };
}
