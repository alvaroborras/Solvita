import React from 'react';
import { Box, Text } from 'ink';
// @ts-ignore — ink-big-text has no types shipped
import BigText from 'ink-big-text';
import { PALETTE, GLYPH } from '../theme.js';
import type { FinalEvent } from '../types.js';

interface VerdictProps {
  event: FinalEvent;
  solutionPath: string | null;
  startedAt: number;
  width: number;
}

function formatDuration(ms: number): string {
  const s = Math.floor(ms / 1000);
  const mm = String(Math.floor(s / 60)).padStart(2, '0');
  const ss = String(s % 60).padStart(2, '0');
  return `${mm}:${ss}`;
}

function estimateCost(prompt: number, completion: number): number {
  // Illustrative pricing only — calibrated to a mid-tier OpenAI-compatible
  // chat model. Override SOLVITA_PRICE_INPUT / SOLVITA_PRICE_OUTPUT
  // (USD per 1M tokens) for your actual provider.
  const inputRate = Number.parseFloat(process.env.SOLVITA_PRICE_INPUT ?? '') || 0.15;
  const outputRate = Number.parseFloat(process.env.SOLVITA_PRICE_OUTPUT ?? '') || 0.60;
  return (prompt * inputRate + completion * outputRate) / 1_000_000;
}

export function Verdict({ event, solutionPath, startedAt, width }: VerdictProps) {
  const won = event.status === 'success' || event.pass_rate === 1.0;
  const wordingMain = won ? 'ACCEPTED' : event.status === 'max_iterations' ? 'MAX ITER' : 'FAILED';
  const color = won ? PALETTE.verdictWin : PALETTE.verdictLose;
  const cost = estimateCost(event.prompt_tokens, event.completion_tokens);
  const elapsed = formatDuration(Date.now() - startedAt);

  const dossier = [
    `${event.iterations} iter`,
    `${event.llm_calls} LLM`,
    `${formatTokens(event.prompt_tokens)} + ${formatTokens(event.completion_tokens)} tok`,
    `$${cost.toFixed(3)}`,
    elapsed,
  ].join('   ·   ');

  const rule = GLYPH.ruleHeavy.repeat(width);
  // `tiny` font keeps the verdict word readable on terminals as narrow as
  // 80 columns; `chrome` rendered as ╔═╗-style boxes that were hard to
  // read at a glance and pushed past 80 cols on long words.
  const verdictFont = 'tiny';

  return (
    <Box flexDirection="column" marginTop={1}>
      <Text color={PALETTE.rule}>{rule}</Text>

      {/* big-text verdict */}
      <Box justifyContent="center" marginY={0}>
        <BigText text={wordingMain} font={verdictFont} colors={[color]} />
      </Box>

      {/* dossier line — centered */}
      <Box justifyContent="center">
        <Text color={PALETTE.meta}>{dossier}</Text>
      </Box>

      {/* solution path */}
      {solutionPath && (
        <Box justifyContent="center" marginTop={1}>
          <Text color={PALETTE.dim}>{solutionPath}</Text>
        </Box>
      )}
    </Box>
  );
}

function formatTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(0)} K`;
  return String(n);
}
