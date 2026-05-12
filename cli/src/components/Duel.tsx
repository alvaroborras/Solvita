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

// ─── Defender (left) row ────────────────────────────────────────────────────

function DefenderRow({ iter }: { iter: DefenderIter }) {
  const iterLabel = iter.iteration < 0 ? '··' : String(iter.iteration + 1).padStart(2, '0');
  const compileLabel =
    iter.compileSuccess === undefined
      ? '—'
      : iter.compileSuccess
        ? 'ok'
        : 'fail';

  return (
    <Box flexDirection="column" marginBottom={1}>
      <Box>
        {statusGlyph(iter.status, PALETTE.defender)}
        <Text color={PALETTE.dim}>{'  '}</Text>
        <Text color={PALETTE.defender} bold>
          {`i${iterLabel}`}
        </Text>
        <Text color={PALETTE.dim}>{iter.patched ? '   ← patching' : ''}</Text>
      </Box>
      {iter.status === 'done' && (
        <>
          <Box>
            <Text color={PALETTE.dim}>{'      compile  '}</Text>
            <Text
              color={iter.compileSuccess ? PALETTE.defender : PALETTE.attacker}
            >
              {compileLabel}
            </Text>
          </Box>
          <Box>
            <Text color={PALETTE.dim}>{'      tests    '}</Text>
            {passDots(iter.passed ?? 0, iter.total ?? 0)}
          </Box>
        </>
      )}
      {iter.status === 'running' && (
        <Box>
          <Text color={PALETTE.dim}>{'      '}</Text>
          <Text color={PALETTE.dim}>generate · ░▒▓█</Text>
        </Box>
      )}
    </Box>
  );
}

// ─── Attacker (right) row ───────────────────────────────────────────────────

function AttackerRow({ round }: { round: AttackerRound }) {
  const roundLabel = `R${String(round.round).padStart(1, '0')}`;
  return (
    <Box flexDirection="column" marginBottom={1}>
      <Box>
        {statusGlyph(round.status, round.landed ? PALETTE.strike : PALETTE.attacker)}
        <Text color={PALETTE.dim}>{'  '}</Text>
        <Text color={round.landed ? PALETTE.strike : PALETTE.attacker} bold>
          {roundLabel}
        </Text>
        {round.status === 'running' && (
          <Text color={PALETTE.dim}>{'   probing …'}</Text>
        )}
      </Box>
      {round.status === 'done' && (
        <Box>
          <Text color={PALETTE.dim}>{'      '}</Text>
          {round.landed ? (
            <Text color={PALETTE.strike}>{'⚡ landed strike'}</Text>
          ) : (
            <Text color={PALETTE.dim}>{'all clear'}</Text>
          )}
        </Box>
      )}
    </Box>
  );
}

// ─── Strike scar (horizontal cross-column line) ─────────────────────────────

function StrikeRow({
  strike,
  width,
  leftWidth,
  rightWidth,
}: {
  strike: Strike;
  width: number;
  leftWidth: number;
  rightWidth: number;
}) {
  // Render: "  ⚡──── STRIKE ────  " spanning the column gap.
  // The line starts from end of defender column, crosses gap, lands in attacker
  // column. We render it as a single Text spanning full width so it visually
  // crosses the boundary.
  const tag = `  ⚡──── STRIKE round R${strike.round}, vs i${String(
    (strike.defenderIter ?? 0) + 1,
  ).padStart(2, '0')} ────`;
  const filler = '─'.repeat(Math.max(0, width - tag.length - 2));
  return (
    <Box>
      <Text color={PALETTE.strike}>{tag}</Text>
      <Text color={PALETTE.dim}>{filler}</Text>
    </Box>
  );
}

// ─── Duel container ─────────────────────────────────────────────────────────

export function Duel({ defender, attacker, strikes, width }: DuelProps) {
  // Title row: DEFENDER · codegen        ATTACKER · hacker
  const colWidth = Math.floor((width - 4) / 2);
  const dot = `${GLYPH.gridDot} `;
  const gridRow = dot.repeat(Math.floor(colWidth / 2));
  const gap = '    ';

  // Determine if there are any strikes to render between specific iters
  // (we render them inline at the bottom of the duel block for now — a future
  // improvement would interleave them at the precise iter boundary)
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
