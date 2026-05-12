import React, { useEffect, useState } from 'react';
import { Box, Text } from 'ink';
import { PALETTE, GLYPH, LAYOUT, spaceCaps } from '../theme.js';

interface HeaderProps {
  problemId: string | null;
  modelLabel?: string;
  startedAt: number;
  tokens: number;
  /** Cumulative-token timeline; rendered as braille sparkline */
  tokenSamples?: number[];
  cost: number | null;
  width: number;
  platformWarning?: boolean;
}

function formatElapsed(ms: number): string {
  const s = Math.floor(ms / 1000);
  const mm = String(Math.floor(s / 60)).padStart(2, '0');
  const ss = String(s % 60).padStart(2, '0');
  return `t+ ${mm}:${ss}`;
}

function formatTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(0)} K`;
  return String(n);
}

function buildSparkline(samples: number[], cols: number): string {
  // Render the *cumulative* token count as a 8-step braille bar column,
  // scaled to local max. For low sample counts pad left with empty.
  if (samples.length === 0) return '─'.repeat(cols);
  const max = Math.max(...samples, 1);
  const padded =
    samples.length < cols
      ? Array(cols - samples.length).fill(0).concat(samples)
      : samples.slice(samples.length - cols);
  return padded
    .map((v) => {
      const idx = Math.max(0, Math.min(7, Math.floor((v / max) * 7)));
      return GLYPH.sparkBars[idx];
    })
    .join('');
}

export function Header({
  problemId,
  modelLabel,
  startedAt,
  tokens,
  tokenSamples,
  cost,
  width,
  platformWarning,
}: HeaderProps) {
  // Tick the clock every second so t+MM:SS stays live
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, []);

  const elapsed = formatElapsed(Date.now() - startedAt);
  const samples = tokenSamples && tokenSamples.length > 0 ? tokenSamples : [tokens];
  const spark = buildSparkline(samples, LAYOUT.sparkColumns);
  const costStr = cost != null ? `$ ${cost.toFixed(3)}` : '';
  const titleSpaced = spaceCaps('SOLVITA');
  const subtitleSpaced = spaceCaps('TELEMETRY');

  return (
    <Box flexDirection="column" marginBottom={1}>
      {/* Title row: SOLVITA · ADVERSARIAL TELEMETRY  ............  spark + tokens */}
      <Box justifyContent="space-between">
        <Box>
          <Text color={PALETTE.text} bold>
            {titleSpaced}
          </Text>
          <Text color={PALETTE.dim}>{'   ·   '}</Text>
          <Text color={PALETTE.meta}>{subtitleSpaced}</Text>
        </Box>
        <Box>
          <Text color={PALETTE.dim}>{'tokens '}</Text>
          <Text color={PALETTE.defender}>{spark}</Text>
          <Text color={PALETTE.text}>{'  '}{formatTokens(tokens)}</Text>
        </Box>
      </Box>

      {/* Heavy rule */}
      <Text color={PALETTE.rule}>{GLYPH.ruleLight.repeat(width)}</Text>

      {/* Meta row: problem · path / model / clock + cost */}
      <Box justifyContent="space-between">
        <Box>
          <Text color={PALETTE.dim}>{'problem  '}</Text>
          <Text color={PALETTE.text}>{problemId ?? '—'}</Text>
        </Box>
        <Box>
          {modelLabel && <Text color={PALETTE.meta}>{modelLabel}</Text>}
          <Text color={PALETTE.dim}>{'   '}</Text>
          <Text color={PALETTE.meta}>{elapsed}</Text>
          {costStr && (
            <>
              <Text color={PALETTE.dim}>{'   ·   '}</Text>
              <Text color={PALETTE.meta}>{costStr}</Text>
            </>
          )}
        </Box>
      </Box>

      {platformWarning && (
        <Box marginTop={1}>
          <Text color={PALETTE.attacker}>
            {'⚠  Windows: C++ rlimit sandbox unavailable; falling back to subprocess mode.'}
          </Text>
        </Box>
      )}
    </Box>
  );
}
