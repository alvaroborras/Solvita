import React from 'react';
import { Box, Text } from 'ink';
import InkSpinner from 'ink-spinner';
import { PALETTE, GLYPH, spaceCaps } from '../theme.js';
import type { ArenaItem } from '../types.js';

interface ArenaProps {
  arena: ArenaItem[];
  width: number;
}

const HEADERS: Record<ArenaItem['key'], string> = {
  abstract_phase: 'ABSTRACT',
  testgen_phase: 'TESTGEN',
  solver_skill_plan: 'PLAN',
};

function StatusGlyph({ status }: { status: ArenaItem['status'] }) {
  if (status === 'running') {
    return (
      <Text color={PALETTE.referee}>
        <InkSpinner type="dots" />
      </Text>
    );
  }
  if (status === 'done') {
    return <Text color={PALETTE.referee}>{GLYPH.done}</Text>;
  }
  return <Text color={PALETTE.dim}>{GLYPH.idle}</Text>;
}

function ConfidenceBar({ conf }: { conf: number }) {
  // Render a single eighth-block for confidence 0..1
  const idx = Math.max(0, Math.min(7, Math.floor(conf * 8)));
  return <Text color={PALETTE.referee}>{GLYPH.barEighths[idx]}</Text>;
}

function ArenaRow({ item }: { item: ArenaItem }) {
  const labelText = `${HEADERS[item.key].padEnd(10)}`;

  let detail: React.ReactNode = <Text color={PALETTE.dim}>—</Text>;

  if (item.status === 'running' || item.status === 'pending') {
    detail = <Text color={PALETTE.dim}>{item.status === 'running' ? '…' : ''}</Text>;
  } else if (item.key === 'abstract_phase') {
    const tags = (item.tags ?? []).join(' · ') || '—';
    const conf = item.confidence ?? 0;
    detail = (
      <Box>
        <Text color={PALETTE.dim}>{'tags  '}</Text>
        <Text color={PALETTE.text}>{tags}</Text>
        <Text color={PALETTE.dim}>{'        conf  '}</Text>
        <Text color={PALETTE.text}>{`${(conf * 100).toFixed(0)} `}</Text>
        <ConfidenceBar conf={conf} />
      </Box>
    );
  } else if (item.key === 'testgen_phase') {
    const n = item.testCount ?? 0;
    const dots = GLYPH.testPass.repeat(Math.min(n, 12));
    detail = (
      <Box>
        <Text color={PALETTE.dim}>{'oracle  '}</Text>
        <Text color={PALETTE.text}>{`${n} cases  `}</Text>
        <Text color={PALETTE.referee}>{dots}</Text>
      </Box>
    );
  } else if (item.key === 'solver_skill_plan') {
    const algo = item.algorithm || '(skill_graph fallback)';
    detail = (
      <Box>
        <Text color={PALETTE.dim}>{'skill_graph → '}</Text>
        <Text color={PALETTE.text}>{algo}</Text>
      </Box>
    );
  }

  return (
    <Box>
      <Text color={PALETTE.text}>{'  '}</Text>
      <StatusGlyph status={item.status} />
      <Text color={PALETTE.dim}>{'   '}</Text>
      <Text color={PALETTE.text} bold>
        {labelText}
      </Text>
      {detail}
    </Box>
  );
}

export function Arena({ arena, width }: ArenaProps) {
  // Always render the three slots in canonical order, even if not yet emitted
  const order: ArenaItem['key'][] = [
    'abstract_phase',
    'testgen_phase',
    'solver_skill_plan',
  ];
  const byKey = new Map(arena.map((a) => [a.key, a]));
  const rendered = order.map(
    (k): ArenaItem =>
      byKey.get(k) ?? {
        key: k,
        label: HEADERS[k],
        status: 'pending',
      },
  );

  // Heavy ARENA rule with embedded label
  const label = ' ARENA ';
  const sideLen = Math.max(2, Math.floor((width - label.length) / 2));
  const headerRule =
    GLYPH.ruleHeavy.repeat(sideLen) +
    label +
    GLYPH.ruleHeavy.repeat(width - sideLen - label.length);
  const footerRule = GLYPH.ruleHeavy.repeat(width);

  return (
    <Box flexDirection="column" marginBottom={1}>
      <Text color={PALETTE.rule}>{headerRule}</Text>
      {rendered.map((item) => (
        <ArenaRow key={item.key} item={item} />
      ))}
      <Text color={PALETTE.rule}>{footerRule}</Text>
    </Box>
  );
}
