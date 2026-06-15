import { describe, expect, it } from 'vitest';
import type { AlgoPilotEvent } from '../types/events';
import { extractRunArtifacts } from './extractRunArtifacts';

describe('extractRunArtifacts', () => {
  it('preserves the last non-null algorithm story across later live artifact snapshots', () => {
    const events: AlgoPilotEvent[] = [
      {
        type: 'artifact_snapshot',
        seq: 1,
        ts: 1,
        data: {
          status: 'pending',
          algorithm_visualization: {
            supported: true,
            family: 'bfs',
            mode: 'teaching',
            sample_source: 'public_test_1',
            sample_focus: '',
            sample_input: '4 3',
            sample_output: '2',
            title: 'Live BFS',
            summary: 'first draft',
            live_cursor: 0,
            live_autoplay: true,
            trace_source: 'deterministic',
            sample_validated: true,
            sample_matches: true,
            validation_note: 'matches sample',
            steps: [
              { step: 1, label: 'start', caption: 'x', state: {} },
              { step: 2, label: 'expand', caption: 'y', state: {} },
            ],
            fallback_text: '',
          },
          solution: {
            code: 'int main() {}',
            version: 1,
            line_count: 1,
          },
        },
      } as AlgoPilotEvent,
      {
        type: 'artifact_snapshot',
        seq: 2,
        ts: 2,
        data: {
          status: 'pending',
          algorithm_visualization: null,
          removed_stage_payload: {
            decision: 'repair',
            feedback_summary: 'Legacy snapshots may still carry removed fields.',
          },
          solution: {
            code: 'int main() {}',
            version: 1,
            line_count: 1,
          },
        },
      } as AlgoPilotEvent,
    ];

    const artifacts = extractRunArtifacts(events);

    expect(artifacts.finalArtifact?.algorithmVisualization?.title).toBe('Live BFS');
    expect(artifacts.finalArtifact?.algorithmVisualization?.liveCursor).toBe(0);
    expect(artifacts.finalArtifact?.algorithmVisualization?.liveAutoplay).toBe(true);
    expect(artifacts.finalArtifact?.algorithmVisualization?.traceSource).toBe('deterministic');
    expect(artifacts.finalArtifact?.algorithmVisualization?.sampleValidated).toBe(true);
    expect(artifacts.finalArtifact?.algorithmVisualization?.sampleMatches).toBe(true);
    expect('removedStagePayload' in (artifacts.finalArtifact || {})).toBe(false);
  });

  it('replaces newer evidence and clears omitted stale arrays, maps, and log tails', () => {
    const oldFailure = {
      input: 'old-input',
      expected_output: '1',
      actual_output: '0',
    };
    const newFailure = {
      input: 'new-input',
      expected_output: '2',
      actual_output: '1',
    };

    const events: AlgoPilotEvent[] = [
      {
        type: 'artifact_snapshot',
        seq: 1,
        ts: 1,
        data: {
          status: 'pending',
          tests: {
            passed_tests: 1,
            total_tests: 2,
            trust_tiers: {
              trusted: 1,
            },
          },
          hack: {
            round: 1,
            failures: [oldFailure],
          },
          execution_log_tail: ['old compile log'],
        },
      } as AlgoPilotEvent,
      {
        type: 'artifact_snapshot',
        seq: 2,
        ts: 2,
        data: {
          status: 'pending',
          tests: {
            passed_tests: 2,
            total_tests: 3,
          },
          hack: {
            round: 2,
            failures: [newFailure],
          },
        },
      } as AlgoPilotEvent,
    ];

    const artifacts = extractRunArtifacts(events);

    expect(artifacts.finalArtifact?.tests.passedTests).toBe(2);
    expect(artifacts.finalArtifact?.tests.totalTests).toBe(3);
    expect(artifacts.finalArtifact?.tests.trustTiers).toEqual({});
    expect(artifacts.finalArtifact?.hack.round).toBe(2);
    expect(artifacts.finalArtifact?.hack.failures).toEqual([newFailure]);
    expect(artifacts.finalArtifact?.executionLogTail).toEqual([]);
  });
});
