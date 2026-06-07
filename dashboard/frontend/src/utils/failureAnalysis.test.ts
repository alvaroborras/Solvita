import { describe, expect, it } from 'vitest';
import type { FinalArtifactSnapshot } from '../types/artifacts';
import type { AlgoPilotEvent } from '../types/events';
import type { JourneyTimelineEntry } from '../types/journey';
import { buildFailureAnalysis } from './failureAnalysis';

function createTimelineEntry(
  stageId: JourneyTimelineEntry['stageId'],
  title: string,
  summary: string,
  status: JourneyTimelineEntry['status'],
  evidence: string[] = [],
): JourneyTimelineEntry {
  return {
    id: `${stageId}-${title}`,
    stageId,
    visit: 1,
    title,
    summary,
    status,
    startedAt: 1,
    endedAt: 2,
    startSeq: 1,
    endSeq: 2,
    steps: [],
    evidence,
    why: [],
  };
}

function createArtifact(): FinalArtifactSnapshot {
  return {
    status: 'max_iterations',
    iteration: 5,
    llmCalls: 3,
    promptTokens: 0,
    completionTokens: 0,
    algorithmVisualization: null,
    solution: {
      code: 'int main() {}',
      version: 2,
      lineCount: 1,
      compilationSuccess: false,
      compilationErrors: ["missing ';' after return", 'unknown identifier n'],
    },
    feedback: {
      analysis: 'The repair loop never fixed the compile-time syntax issue near the return statement.',
      errorPattern: 'syntax_error',
      suggestedFixes: ['Add the missing semicolon.', 'Declare the missing variable before use.'],
    },
    tests: {
      publicTests: [],
      generatedTests: [],
      passedTests: 0,
      totalTests: 1,
      passRate: 0,
      fullTestgenCompleted: false,
      trustTiers: {},
    },
    verification: {
      decision: 'repair',
      confidence: 0.22,
      feedbackSummary: 'Trusted checks still indicate the solver is unsafe.',
      riskFlags: ['trusted_suite_failed'],
      trustedFailures: [],
    },
    hack: {
      result: null,
      passed: null,
      round: null,
      failures: [],
      generatorFailureKind: null,
      generatorFailureReason: null,
    },
    executionLogTail: ['Compilation failed: 2 error(s)', 'Feedback analyzed'],
  };
}

describe('buildFailureAnalysis', () => {
  it('builds a max-iterations failure chain with compile and verifier evidence', () => {
    const analysis = buildFailureAnalysis({
      finalStatus: 'max_iterations',
      artifact: createArtifact(),
      timeline: [
        createTimelineEntry('codegen', 'Generating & Testing Code', 'Attempt 3 failed to compile cleanly and needs repair.', 'repairing', ['Compile status: failure']),
        createTimelineEntry('verify', 'Independent Verification', 'The verifier requested a repair before acceptance.', 'repairing', ['Verifier decision: repair']),
      ],
      events: [],
    });

    expect(analysis).not.toBeNull();
    expect(analysis?.headline).toBe('The solver ran out of repair budget.');
    expect(analysis?.rootCause).toContain('compile-time syntax issue');
    expect(analysis?.chain.map((item) => item.stageLabel)).toEqual(['Codegen', 'Verify', 'Run Ended']);
    expect(analysis?.signals.compilationErrors).toContain("missing ';' after return");
    expect(analysis?.signals.suggestedFixes).toContain('Add the missing semicolon.');
  });

  it('surfaces hack-stage terminal failures as the primary root cause', () => {
    const artifact = createArtifact();
    artifact.status = 'terminal_failure';
    artifact.solution.compilationSuccess = true;
    artifact.solution.compilationErrors = [];
    artifact.feedback.analysis = '';
    artifact.hack.result = 'BREAK';
    artifact.hack.passed = false;
    artifact.hack.round = 2;
    artifact.hack.failures = [
      {
        input: '4 4\n1 2\n2 3\n3 4\n4 1\n',
        expected_output: '2\n',
        actual_output: '3\n',
        failure_type: 'WA',
        details: 'Cycle handling is incorrect.',
      },
    ];

    const analysis = buildFailureAnalysis({
      finalStatus: 'terminal_failure',
      artifact,
      timeline: [
        createTimelineEntry('hack', 'Adversarial Hack Testing', 'Hack round 2 found a breaking case and sent the solver back for repair.', 'repairing', ['Failure type: WA']),
      ],
      events: [],
    });

    expect(analysis?.headline).toBe('A hack-stage counterexample broke the candidate.');
    expect(analysis?.rootCause).toContain('Cycle handling is incorrect.');
    expect(analysis?.signals.hackFailures).toHaveLength(1);
  });

  it('shows runtime crash information even when no final artifact is emitted', () => {
    const events: AlgoPilotEvent[] = [
      {
        type: 'error',
        seq: 9,
        ts: 100,
        message: 'Workflow execution failed: sandbox timeout',
        traceback: 'Traceback...',
      } as AlgoPilotEvent,
    ];

    const analysis = buildFailureAnalysis({
      finalStatus: null,
      artifact: null,
      timeline: [
        createTimelineEntry('codegen', 'Generating & Testing Code', 'Running the current draft against the available suite.', 'active'),
      ],
      events,
    });

    expect(analysis?.headline).toBe('The workflow crashed before a final verdict.');
    expect(analysis?.rootCause).toContain('sandbox timeout');
    expect(analysis?.signals.errorEvents).toContain('Workflow execution failed: sandbox timeout');
    expect(analysis?.chain[analysis.chain.length - 1]?.stageLabel).toBe('System');
  });

  it('surfaces live repair diagnostics before the run has ended', () => {
    const analysis = buildFailureAnalysis({
      finalStatus: null,
      artifact: createArtifact(),
      timeline: [
        createTimelineEntry('codegen', 'Generating & Testing Code', 'Attempt 2 failed to compile cleanly and needs repair.', 'repairing', ['Compile status: failure']),
      ],
      events: [],
    });

    expect(analysis).not.toBeNull();
    expect(analysis?.headline).toBe('The current attempt is failing and being repaired.');
    expect(analysis?.rootCause).toContain('compile-time syntax issue');
    expect(analysis?.chain[0]?.stageLabel).toBe('Codegen');
  });

  it('returns null for successful runs', () => {
    const analysis = buildFailureAnalysis({
      finalStatus: 'success',
      artifact: createArtifact(),
      timeline: [],
      events: [],
    });

    expect(analysis).toBeNull();
  });

  it('returns null for cancelled runs', () => {
    const analysis = buildFailureAnalysis({
      finalStatus: 'cancelled',
      artifact: createArtifact(),
      timeline: [],
      events: [],
    });

    expect(analysis).toBeNull();
  });
});
