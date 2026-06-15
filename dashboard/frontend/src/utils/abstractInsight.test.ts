import { describe, expect, it } from 'vitest';
import type { AlgoPilotEvent } from '../types/events';
import { extractAbstractInsight } from './abstractInsight';

describe('extractAbstractInsight', () => {
  it('uses the latest abstract phase result tags and confidence', () => {
    const events: AlgoPilotEvent[] = [
      {
        type: 'phase_done',
        phase: 'abstract_phase',
        seq: 1,
        ts: 1,
        data: { tags: ['graphs', 'bfs'], confidence: 0.71 },
      },
      {
        type: 'phase_done',
        phase: 'codegen_phase',
        seq: 2,
        ts: 2,
        data: { passed: 2, total: 3 },
      },
      {
        type: 'phase_done',
        phase: 'abstract_phase',
        seq: 3,
        ts: 3,
        data: { tags: ['dp', 'math', 'dp', ''], confidence: 0.92 },
      },
    ];

    expect(extractAbstractInsight(events)).toEqual({
      tags: ['dp', 'math'],
      confidence: 0.92,
    });
  });
});
