import React from 'react';
import { Box, Text } from 'ink';
import InkSpinner from 'ink-spinner';
import { PALETTE, GLYPH, spaceCaps } from '../theme.js';
import type { DefenderIter, AttackerRound, Strike } from '../types.js';

interface DuelProps {
  defender: DefenderIter[];
  attacker: AttackerRound[];
  strikes: Strike[];
  width: number;        // total inner width available
}

// ─── Glyph helpers ──────────────────────────────────────────────────────────

function statusGlyph(status: 'running' | 'done' | 'pending' | 'error', color: string) {
  if (status === 'running') {
    return (
      <Text color={color}>
        <InkSpinner type="dots" />
      </Text>
    );
  }
  if (status === 'done') {
    return <Text color={color}>{GLYPH.done}</Text>;
  }
  if (status === 'error') {
    return <Text color={PALETTE.verdictError}>{GLYPH.retry}</Text>;
  }
  return <Text color={PALETTE.dim}>{GLYPH.idle}</Text>;
}

function passDots(passed: number, total: number, max = 12): React.ReactNode {
  if (total <= 0) {
    return <Text color={PALETTE.dim}>—</Text>;
  }
  const shown = Math.min(total, max);
  const passedShown = Math.round((passed / total) * shown);
  const dots =
    GLYPH.testPass.repeat(passedShown) +
    GLYPH.testFail.repeat(Math.max(0, shown - passedShown));
  return (
    <Box>
      {[...dots].map((ch, i) => (
        <Text key={i} color={ch === GLYPH.testPass ? PALETTE.defender : PALETTE.dim}>
          {ch}
        </Text>
      ))}
      <Text color={PALETTE.dim}>{`  ${passed}/${total}`}</Text>
    </Box>
  );
}

// ─── Defender (left) row — single line per iteration ──────────────────────
//   ◆  i01  compile ✓  ●●●  3/3  100% ▉▉▉▉▎····
// Status glyph + iter number + compile result + pass dots + ratio + bar.
// Patched marker is shown by the `◇` retry glyph (handled by statusGlyph).

function DefenderRow({ iter }: { iter: DefenderIter }) {
  const iterLabel = iter.iteration < 0 ? '··' : String(iter.iteration + 1).padStart(2, '0');
  const showCompile = iter.compileSuccess !== undefined;
  const showTests = (iter.total ?? 0) > 0;
  const passed = iter.passed ?? 0;
  const total = iter.total ?? 0;
  const passRate = iter.passRate ?? 0;

  return (
    <Box>
      {statusGlyph(iter.status, iter.patched ? PALETTE.strike : PALETTE.defender)}
      <Text color={PALETTE.dim}>{'  '}</Text>
      <Text color={PALETTE.defender} bold>
        {`i${iterLabel}`}
      </Text>
      {iter.status === 'running' ? (
        <>
          <Text color={PALETTE.dim}>{'  ░▒▓█ '}</Text>
          <Text color={PALETTE.meta}>{'generate'}</Text>
        </>
      ) : (
        <>
          {showCompile && (
            <>
              <Text color={PALETTE.dim}>{'  '}</Text>
              <Text color={iter.compileSuccess ? PALETTE.defender : PALETTE.attacker}>
                {iter.compileSuccess ? '✓' : '✗'}
              </Text>
            </>
          )}
          {showTests && (
            <>
              <Text color={PALETTE.dim}>{'  '}</Text>
              {renderTestDots(passed, total, 6)}
              <Text color={PALETTE.dim}>{' '}</Text>
              <Text color={PALETTE.text}>{`${passed}/${total}`}</Text>
              <Text color={PALETTE.dim}>{'  '}</Text>
              <Text color={passRate >= 1 ? PALETTE.defender : PALETTE.attacker}>
                {`${(passRate * 100).toFixed(0)}%`}
              </Text>
            </>
          )}
        </>
      )}
    </Box>
  );
}

function renderTestDots(passed: number, total: number, max = 6): React.ReactNode {
  if (total <= 0) return <Text color={PALETTE.dim}>—</Text>;
  const shown = Math.min(total, max);
  const passedShown = Math.round((passed / total) * shown);
  return (
    <Box>
      <Text color={PALETTE.defender}>{GLYPH.testPass.repeat(passedShown)}</Text>
      <Text color={PALETTE.attacker}>{GLYPH.testFail.repeat(Math.max(0, shown - passedShown))}</Text>
    </Box>
  );
}

// ─── Attacker (right) row — single line per round ─────────────────────────
//   ◆  R1  STRIKE        (or)
//   ◆  R1  clean
//   ▶  R2  probing

function AttackerRow({ round }: { round: AttackerRound }) {
  const roundLabel = `R${String(round.round).padStart(1, '0')}`;
  const tone = round.landed ? PALETTE.strike : PALETTE.attacker;

  return (
    <Box>
      {statusGlyph(round.status, tone)}
      <Text color={PALETTE.dim}>{'  '}</Text>
      <Text color={tone} bold>
        {roundLabel}
      </Text>
      {round.status === 'running' && (
        <Text color={PALETTE.meta}>{'   probing'}</Text>
      )}
      {round.status === 'done' && round.landed === true && (
        <>
          <Text color={PALETTE.dim}>{'   ⚡ '}</Text>
          <Text color={PALETTE.strike} bold>{'STRIKE'}</Text>
        </>
      )}
      {round.status === 'done' && round.landed === false && (
        <Text color={PALETTE.meta}>{'   clean'}</Text>
      )}
    </Box>
  );
}

// ─── Strike scar (horizontal cross-column line) ─────────────────────────────

// ─── Strike scar — single horizontal scar that NEVER wraps ────────────────
//   ⚡  STRIKE  R1 → i01  ·  WA ──────────────────────────────────────────
//
// Width math: the leading ⚡ glyph and the trailing ⚡ are wide chars
// (2 cells each on most terminals). We compute filler conservatively so
// total cell width ≤ width − 4 (4-cell safety margin).

function StrikeRow({
  strike,
  width,
}: {
  strike: Strike;
  width: number;
  leftWidth: number;
  rightWidth: number;
}) {
  const verdict = (strike.failureType ?? 'BREAK').toUpperCase();
  // Tag = "  ⚡  STRIKE  R{n} → i{NN}  ·  {VERDICT}  "
  // Visible cells: 2 leading + 2 (⚡) + 2 + 6 + 2 + 2 + len(R{n}) + 4 +
  //                len(i{NN}) + 4 + 1 + len(verdict) + 2 = roughly 30 + len
  const tagText = `  ⚡  STRIKE  R${strike.round} → i${String(
    (strike.defenderIter ?? 0) + 1,
  ).padStart(2, '0')}  ·  ${verdict}  `;
  // Account for the wide ⚡ (visible cell count = string length + 1)
  const tagCells = tagText.length + 1;
  const filler = '─'.repeat(Math.max(0, width - tagCells - 2));

  return (
    <Box flexDirection="column">
      <Box>
        <Text color={PALETTE.strike} bold>
          {tagText}
        </Text>
        <Text color={PALETTE.strike}>{filler}</Text>
      </Box>
      {strike.failingInputHead && (
        <Box marginLeft={4}>
          <Text color={PALETTE.meta}>{'input    '}</Text>
          <Text color={PALETTE.text}>{fitOneLine(strike.failingInputHead, width - 14)}</Text>
        </Box>
      )}
      {strike.expectedHead && (
        <Box marginLeft={4}>
          <Text color={PALETTE.meta}>{'expected '}</Text>
          <Text color={PALETTE.defender}>{fitOneLine(strike.expectedHead, width - 14)}</Text>
        </Box>
      )}
      {strike.actualHead && (
        <Box marginLeft={4}>
          <Text color={PALETTE.meta}>{'got      '}</Text>
          <Text color={PALETTE.attacker}>{fitOneLine(strike.actualHead, width - 14)}</Text>
        </Box>
      )}
    </Box>
  );
}

function fitOneLine(s: string, max: number): string {
  const collapsed = s.replace(/\s+/g, ' ').trim();
  if (collapsed.length <= max || max <= 1) return collapsed.slice(0, Math.max(0, max));
  return collapsed.slice(0, max - 1) + '…';
}

// ─── Duel container ─────────────────────────────────────────────────────────

export function Duel({ defender, attacker, strikes, width }: DuelProps) {
  // Two columns each gets (width - 4) / 2; floor it. Each column has paddingX=1
  // (consumes 2 cells per column). Dot grid budget = colWidth - 4 (3-cell
  // indent + 1-cell right safety) and "· " is 2 cells per dot.
  const colWidth = Math.floor((width - 4) / 2);
  const dotsPerCol = Math.max(0, Math.floor((colWidth - 4) / 2));
  const gridRow = `${GLYPH.gridDot} `.repeat(dotsPerCol);
  const gap = '    ';

  const hasStrike = strikes.length > 0;

  return (
    <Box flexDirection="column">
      {/* Column titles */}
      <Box>
        <Box width={colWidth}>
          <Text color={PALETTE.defender} bold>
            {`     ${spaceCaps('DEFENDER')}`}
          </Text>
          <Text color={PALETTE.dim}>{'  · codegen'}</Text>
        </Box>
        <Text>{gap}</Text>
        <Box width={colWidth}>
          <Text color={PALETTE.attacker} bold>
            {`     ${spaceCaps('ATTACKER')}`}
          </Text>
          <Text color={PALETTE.dim}>{'  · hacker'}</Text>
        </Box>
      </Box>

      {/* Dot-grid background row */}
      <Box>
        <Box width={colWidth}>
          <Text color={PALETTE.grid}>{`   ${gridRow}`}</Text>
        </Box>
        <Text>{gap}</Text>
        <Box width={colWidth}>
          <Text color={PALETTE.grid}>{`   ${gridRow}`}</Text>
        </Box>
      </Box>

      {/* Two columns side-by-side */}
      <Box>
        <Box flexDirection="column" width={colWidth} paddingX={1}>
          {defender.length === 0 ? (
            <Text color={PALETTE.dim}>{'   awaiting first iteration …'}</Text>
          ) : (
            defender.map((iter, idx) => (
              <DefenderRow key={`d-${idx}`} iter={iter} />
            ))
          )}
        </Box>
        <Text>{gap}</Text>
        <Box flexDirection="column" width={colWidth} paddingX={1}>
          {attacker.length === 0 ? (
            <Text color={PALETTE.dim}>{'   no rounds yet …'}</Text>
          ) : (
            attacker.map((round, idx) => (
              <AttackerRow key={`a-${idx}`} round={round} />
            ))
          )}
        </Box>
      </Box>

      {/* Persistent strike scars (always at the bottom of the duel block) */}
      {hasStrike && (
        <Box flexDirection="column" marginTop={1}>
          {strikes.map((s, i) => (
            <StrikeRow
              key={`s-${i}`}
              strike={s}
              width={width}
              leftWidth={colWidth}
              rightWidth={colWidth}
            />
          ))}
        </Box>
      )}
    </Box>
  );
}
