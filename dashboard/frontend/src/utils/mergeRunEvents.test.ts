import { describe, expect, it } from 'vitest';

import { mergeRunEvents } from './mergeRunEvents';

describe('mergeRunEvents', () => {
  it('dedupes by seq and keeps ascending order', () => {
    const result = mergeRunEvents(
      [
        { type: 'solve_start', seq: 0, ts: 1 },
        { type: 'phase_start', phase: 'codegen_phase', seq: 3, ts: 4 },
      ],
      [
        { type: 'phase_start', phase: 'codegen_phase', seq: 3, ts: 4 },
        { type: 'phase_done', phase: 'codegen_phase', seq: 4, ts: 5, data: {} },
        { type: 'phase_start', phase: 'testgen_phase', seq: 1, ts: 2 },
      ],
    );

    expect(result.map((event) => event.seq)).toEqual([0, 1, 3, 4]);
  });
});
