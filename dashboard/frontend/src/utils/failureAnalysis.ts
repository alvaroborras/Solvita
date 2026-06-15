import type { FinalArtifactSnapshot, ArtifactFailureCase } from '../types/artifacts';
import type { AlgoPilotEvent } from '../types/events';
import type { JourneyStageId, JourneyTimelineEntry } from '../types/journey';

export interface FailureAnalysisSignalSet {
  suggestedFixes: string[];
  compilationErrors: string[];
  errorEvents: string[];
  hackFailures: string[];
  executionLogTail: string[];
}

export interface FailureChainItem {
  id: string;
  stageLabel: string;
  title: string;
  summary: string;
  status: 'warning' | 'failed' | 'error';
  evidence: string[];
}

export interface FailureAnalysis {
  headline: string;
  summary: string;
  rootCause: string;
  chain: FailureChainItem[];
  signals: FailureAnalysisSignalSet;
}

interface BuildFailureAnalysisArgs {
  finalStatus: string | null;
  artifact: FinalArtifactSnapshot | null;
  timeline: JourneyTimelineEntry[];
  events: AlgoPilotEvent[];
}

const STAGE_LABELS: Record<JourneyStageId, string> = {
  read_problem: 'Read Problem',
  full_testgen: 'Full Testgen',
  codegen: 'Codegen',
  hack: 'Hack',
};

export function buildFailureAnalysis({
  finalStatus,
  artifact,
  timeline,
  events,
}: BuildFailureAnalysisArgs): FailureAnalysis | null {
  if (finalStatus === 'success' || finalStatus === 'cancelled') {
    return null;
  }

  const errorEvents = events
    .filter((event) => event.type === 'error')
    .map((event) => String((event as Record<string, unknown>).message || 'Unknown workflow error'));

  const liveFailure =
    Boolean(artifact?.solution.compilationSuccess === false && (artifact?.solution.compilationErrors.length || 0) > 0)
    || Boolean((artifact?.hack.failures.length || 0) > 0)
    || Boolean((artifact?.hack.result || '') === 'BREAK')
    || Boolean((artifact?.hack.result || '') === 'GEN_FAILED');

  const failed =
    Boolean(finalStatus && finalStatus !== 'success')
    || liveFailure
    || errorEvents.length > 0;

  if (!failed) {
    return null;
  }

  const signals: FailureAnalysisSignalSet = {
    suggestedFixes: artifact?.feedback.suggestedFixes || [],
    compilationErrors: artifact?.solution.compilationErrors || [],
    errorEvents,
    hackFailures: (artifact?.hack.failures || []).map(formatFailureCase),
    executionLogTail: artifact?.executionLogTail || [],
  };

  const chain = buildFailureChain(finalStatus, artifact, timeline, errorEvents);
  const rootCause = chooseRootCause(finalStatus, artifact, signals);
  const { headline, summary } = describeFailure(finalStatus, artifact, errorEvents, rootCause);

  return {
    headline,
    summary,
    rootCause,
    chain,
    signals,
  };
}

function buildFailureChain(
  finalStatus: string | null,
  artifact: FinalArtifactSnapshot | null,
  timeline: JourneyTimelineEntry[],
  errorEvents: string[],
): FailureChainItem[] {
  const interesting = timeline.filter((entry) =>
    entry.status === 'repairing'
      || entry.status === 'failed'
      || entry.stageId === 'codegen'
      || entry.stageId === 'hack',
  );

  const chain: FailureChainItem[] = interesting.slice(-4).map((entry) => ({
    id: entry.id,
    stageLabel: STAGE_LABELS[entry.stageId],
    title: entry.title,
    summary: entry.summary,
    status: entry.status === 'failed' ? 'failed' : entry.status === 'repairing' ? 'warning' : 'warning',
    evidence: entry.evidence.slice(0, 3),
  }));

  if (finalStatus === 'max_iterations') {
    chain.push({
      id: 'run-ended-max-iterations',
      stageLabel: 'Run Ended',
      title: 'Repair budget exhausted',
      summary: 'The workflow hit the iteration cap before it could produce an accepted solution.',
      status: 'failed',
      evidence: [
        `iterations: ${artifact?.iteration ?? '—'}`,
        artifact?.tests.passRate !== undefined ? `visible pass rate: ${Math.round(artifact.tests.passRate * 100)}%` : '',
      ].filter(Boolean),
    });
  } else if (finalStatus === 'terminal_failure') {
    chain.push({
      id: 'run-ended-terminal-failure',
      stageLabel: 'Run Ended',
      title: 'Terminal failure after hack',
      summary: 'A late-stage adversarial counterexample broke the candidate and the workflow stopped.',
      status: 'failed',
      evidence: [
        artifact?.hack.result ? `hack result: ${artifact.hack.result}` : '',
        artifact?.hack.round ? `hack round: ${artifact.hack.round}` : '',
      ].filter(Boolean),
    });
  }

  if (errorEvents.length > 0) {
    chain.push({
      id: 'system-error',
      stageLabel: 'System',
      title: 'Workflow runtime error',
      summary: errorEvents[0],
      status: 'error',
      evidence: errorEvents.slice(1, 3),
    });
  }

  return chain;
}

function chooseRootCause(
  finalStatus: string | null,
  artifact: FinalArtifactSnapshot | null,
  signals: FailureAnalysisSignalSet,
): string {
  if (signals.errorEvents.length > 0) {
    return signals.errorEvents[0];
  }

  if (finalStatus === 'terminal_failure' && signals.hackFailures.length > 0) {
    return signals.hackFailures[0];
  }

  if (signals.compilationErrors.length > 0) {
    return artifact?.feedback.analysis || signals.compilationErrors[0];
  }

  if (artifact?.feedback.analysis) {
    return artifact.feedback.analysis;
  }

  if (artifact?.hack.generatorFailureReason) {
    return artifact.hack.generatorFailureReason;
  }

  if (signals.executionLogTail.length > 0) {
    return signals.executionLogTail[signals.executionLogTail.length - 1];
  }

  if (finalStatus === 'max_iterations') {
    return 'The workflow kept repairing the candidate, but never gathered enough evidence to accept it before the iteration budget ran out.';
  }

  if (finalStatus === 'terminal_failure') {
    return 'A final adversarial test exposed a bug that the workflow could not repair in time.';
  }

  return 'The workflow stopped without producing a trustworthy accepted solution.';
}

function describeFailure(
  finalStatus: string | null,
  artifact: FinalArtifactSnapshot | null,
  errorEvents: string[],
  rootCause: string,
): { headline: string; summary: string } {
  if (errorEvents.length > 0) {
    return {
      headline: 'The workflow crashed before a final result.',
      summary: 'A runtime-level error interrupted the solve loop, so the run ended without a clean final decision.',
    };
  }

  if (finalStatus === 'max_iterations') {
    return {
      headline: 'The solver ran out of repair budget.',
      summary: 'The run kept looping through codegen and repair, but never reached an accepted solution before the iteration budget ran out.',
    };
  }

  if (finalStatus === 'terminal_failure') {
    return {
      headline: 'A hack-stage counterexample broke the candidate.',
      summary: artifact?.hack.failures?.[0]?.details
        || 'The candidate looked acceptable until adversarial testing produced a concrete breaking input.',
    };
  }

  if (artifact?.solution.compilationSuccess === false && artifact.solution.compilationErrors.length > 0) {
    return {
      headline: 'The current attempt is failing and being repaired.',
      summary: artifact.feedback.analysis
        || 'Compilation failed on the current draft, and the agent is analyzing how to patch the code.',
    };
  }

  if ((artifact?.hack.failures.length || 0) > 0 || artifact?.hack.result === 'BREAK') {
    return {
      headline: 'The hacker found a live counterexample.',
      summary: artifact?.hack.failures?.[0]?.details
        || 'Adversarial testing produced a breaking input that sent the solver back into repair.',
    };
  }

  if (artifact?.hack.result === 'GEN_FAILED') {
    return {
      headline: 'Hack generation is blocked right now.',
      summary: artifact.hack.generatorFailureReason
        || 'The hack pipeline could not produce a valid adversarial candidate on this pass.',
    };
  }

  return {
    headline: 'The run ended without an accepted solution.',
    summary: rootCause,
  };
}

function formatFailureCase(failure: ArtifactFailureCase): string {
  const parts = [
    failure.failure_type ? `type: ${failure.failure_type}` : '',
    failure.details || '',
    failure.stderr || '',
    failure.expected_output && failure.actual_output
      ? `expected ${failure.expected_output.trim()} / actual ${failure.actual_output.trim()}`
      : '',
  ].filter(Boolean);

  return parts.join(' | ') || 'failure case recorded';
}
