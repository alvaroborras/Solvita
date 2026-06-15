import { describe, expect, it } from 'vitest';

import type { FinalArtifactSnapshot } from '../types/artifacts';
import type { AlgoPilotEvent } from '../types/events';
import { buildSolveJourney } from './buildSolveJourney';
import { buildLiveProgress } from './buildLiveProgress';
import { extractRunArtifacts } from './extractRunArtifacts';

function createArtifact(overrides: Partial<FinalArtifactSnapshot> = {}): FinalArtifactSnapshot {
  return {
    status: 'pending',
    iteration: null,
    llmCalls: null,
    promptTokens: null,
    completionTokens: null,
    algorithmVisualization: null,
    solution: {
      code: '',
      version: 0,
      lineCount: 0,
      compilationSuccess: null,
      compilationErrors: [],
    },
    feedback: {
      analysis: null,
      errorPattern: null,
      suggestedFixes: [],
    },
    tests: {
      publicTests: [],
      generatedTests: [],
      passedTests: 0,
      totalTests: 0,
      passRate: 0,
      fullTestgenCompleted: false,
      trustTiers: {},
    },
    hack: {
      result: null,
      passed: null,
      round: null,
      failures: [],
      generatorFailureKind: null,
      generatorFailureReason: null,
    },
    executionLogTail: [],
    ...overrides,
  };
}

describe('buildLiveProgress', () => {
  it('reports the active stage and current step from canonical events', () => {
    const progress = buildLiveProgress({
      events: [
        { type: 'solve_start', seq: 0, ts: 1, problem_id: 'p1' },
        { type: 'phase_start', phase: 'codegen_phase', seq: 1, ts: 2 },
        { type: 'node_enter', node_id: 'compile_code', subgraph: 'codegen', seq: 2, ts: 3 },
      ] as AlgoPilotEvent[],
      artifact: createArtifact({
        iteration: 2,
        tests: {
          publicTests: [],
          generatedTests: [],
          passedTests: 7,
          totalTests: 9,
          passRate: 7 / 9,
          fullTestgenCompleted: true,
          trustTiers: {},
        },
      }),
    });

    expect(progress.stageId).toBe('codegen');
    expect(progress.currentStepLabel).toContain('Compile');
    expect(progress.currentStepSummary).toMatch(/build/i);
    expect(progress.metrics.iteration).toBe(2);
    expect(progress.metrics.passed).toBe(7);
    expect(progress.metrics.total).toBe(9);
  });

  it('keeps the latest known metrics when later artifact snapshots omit them', () => {
    const events = [
      { type: 'phase_start', phase: 'codegen_phase', seq: 0, ts: 1 },
      { type: 'node_enter', node_id: 'compile_code', subgraph: 'codegen', seq: 1, ts: 2 },
      {
        type: 'artifact_snapshot',
        seq: 2,
        ts: 3,
        data: {
          status: 'pending',
          iteration: 2,
          tests: {
            public_tests: [],
            generated_tests: [],
            passed_tests: 7,
            total_tests: 9,
            pass_rate: 7 / 9,
            full_testgen_completed: true,
            trust_tiers: {},
          },
          hack: {
            result: 'repair',
            passed: false,
            round: 1,
            failures: [],
            generator_failure_kind: null,
            generator_failure_reason: null,
          },
          execution_log_tail: ['Compile passed'],
        },
      },
      {
        type: 'artifact_snapshot',
        seq: 3,
        ts: 4,
        data: {
          status: 'pending',
          execution_log_tail: ['Still compiling hotfix'],
        },
      },
    ] as AlgoPilotEvent[];

    const artifact = extractRunArtifacts(events).finalArtifact;
    const progress = buildLiveProgress({ events, artifact });

    expect(artifact?.tests.passedTests).toBe(7);
    expect(artifact?.tests.totalTests).toBe(9);
    expect(artifact?.hack.round).toBe(1);
    expect(progress.metrics.iteration).toBe(2);
    expect(progress.metrics.passed).toBe(7);
    expect(progress.metrics.total).toBe(9);
    expect(progress.metrics.resultStatus).toBe('pending');
    expect(progress.metrics.hackRound).toBe(1);
    expect(progress.currentStepSummary).toBe('Still compiling hotfix');
  });

  it('does not show a stale codegen log line after the event stream advances to verify', () => {
    const progress = buildLiveProgress({
      events: [
        { type: 'phase_start', phase: 'codegen_phase', label: 'Generating & Testing Code', seq: 0, ts: 1 },
        { type: 'node_enter', node_id: 'compile_code', subgraph: 'codegen', seq: 1, ts: 2 },
        { type: 'phase_start', phase: 'hacker_phase', label: 'Adversarial Hack', seq: 2, ts: 3 },
      ] as AlgoPilotEvent[],
      artifact: createArtifact({
        iteration: 2,
        executionLogTail: ['Compilation failed: expected \';\' before \'}\' token'],
      }),
    });

    expect(progress.stageId).toBe('hack');
    expect(progress.currentStepLabel).toBe('Adversarial Hack');
    expect(progress.currentStepSummary).not.toContain('Compilation failed');
    expect(progress.currentStepSummary).toBe('Try to break the accepted-looking solution with adversarial inputs.');
  });
});

describe('buildSolveJourney', () => {
  it('closes the final hack lesson step when the run finishes successfully', () => {
    const journey = buildSolveJourney([
      { type: 'solve_start', problem_id: 'p1', seq: 0, ts: 1 },
      { type: 'phase_start', phase: 'hacker_phase', label: 'Adversarial Hack', seq: 1, ts: 2 },
      { type: 'node_enter', node_id: 'settle_hacker_memory', subgraph: 'hacker', seq: 2, ts: 3 },
      { type: 'final', status: 'success', iterations: 1, passed: 3, total: 3, pass_rate: 1, seq: 3, ts: 4 },
    ] as AlgoPilotEvent[]);

    const hackEntry = journey.timeline.find((entry) => entry.stageId === 'hack');
    const hackStage = journey.stages.find((stage) => stage.id === 'hack');

    expect(journey.activeStageId).toBeNull();
    expect(hackEntry?.status).toBe('completed');
    expect(hackEntry?.steps[hackEntry.steps.length - 1]).toMatchObject({
      label: 'Record hack lessons',
      status: 'completed',
    });
    expect(hackStage?.status).toBe('completed');
  });

  it('marks an open hack lesson step as failed when the run ends unsuccessfully', () => {
    const journey = buildSolveJourney([
      { type: 'solve_start', problem_id: 'p1', seq: 0, ts: 1 },
      { type: 'phase_start', phase: 'hacker_phase', label: 'Adversarial Hack', seq: 1, ts: 2 },
      { type: 'node_enter', node_id: 'settle_hacker_memory', subgraph: 'hacker', seq: 2, ts: 3 },
      { type: 'final', status: 'terminal_failure', iterations: 1, passed: 2, total: 3, pass_rate: 2 / 3, seq: 3, ts: 4 },
    ] as AlgoPilotEvent[]);

    const hackEntry = journey.timeline.find((entry) => entry.stageId === 'hack');
    const hackStage = journey.stages.find((stage) => stage.id === 'hack');

    expect(journey.activeStageId).toBeNull();
    expect(hackEntry?.status).toBe('failed');
    expect(hackEntry?.steps[hackEntry.steps.length - 1]).toMatchObject({
      label: 'Record hack lessons',
      status: 'failed',
    });
    expect(hackStage?.status).toBe('failed');
  });

  it('does not mark unseen earlier stages as skipped when a restored log begins mid-run', () => {
    const journey = buildSolveJourney([
      { type: 'phase_start', phase: 'codegen_phase', seq: 10, ts: 100 },
      { type: 'node_enter', node_id: 'compile_code', subgraph: 'codegen', seq: 11, ts: 101 },
    ] as AlgoPilotEvent[]);

    expect(journey.activeStageId).toBe('codegen');
    expect(journey.stages.find((stage) => stage.id === 'read_problem')?.status).toBe('waiting');
    expect(journey.stages.find((stage) => stage.id === 'full_testgen')?.status).toBe('waiting');
  });
});
