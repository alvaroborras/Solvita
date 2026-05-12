import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { Box, Text } from 'ink';
import InkSpinner from 'ink-spinner';
import { PALETTE, GLYPH, spaceCaps } from '../theme.js';
// ─── Glyph helpers ──────────────────────────────────────────────────────────
function statusGlyph(status, color) {
    if (status === 'running') {
        return (_jsx(Text, { color: color, children: _jsx(InkSpinner, { type: "dots" }) }));
    }
    if (status === 'done') {
        return _jsx(Text, { color: color, children: GLYPH.done });
    }
    if (status === 'error') {
        return _jsx(Text, { color: PALETTE.verdictError, children: GLYPH.retry });
    }
    return _jsx(Text, { color: PALETTE.dim, children: GLYPH.idle });
}
function passDots(passed, total, max = 12) {
    if (total <= 0) {
        return _jsx(Text, { color: PALETTE.dim, children: "\u2014" });
    }
    const shown = Math.min(total, max);
    const passedShown = Math.round((passed / total) * shown);
    const dots = GLYPH.testPass.repeat(passedShown) +
        GLYPH.testFail.repeat(Math.max(0, shown - passedShown));
    return (_jsxs(Box, { children: [[...dots].map((ch, i) => (_jsx(Text, { color: ch === GLYPH.testPass ? PALETTE.defender : PALETTE.dim, children: ch }, i))), _jsx(Text, { color: PALETTE.dim, children: `  ${passed}/${total}` })] }));
}
// ─── Defender (left) row — single line per iteration ──────────────────────
//   ◆  i01  compile ✓  ●●●  3/3  100% ▉▉▉▉▎····
// Status glyph + iter number + compile result + pass dots + ratio + bar.
// Patched marker is shown by the `◇` retry glyph (handled by statusGlyph).
function DefenderRow({ iter }) {
    const iterLabel = iter.iteration < 0 ? '··' : String(iter.iteration + 1).padStart(2, '0');
    const showCompile = iter.compileSuccess !== undefined;
    const showTests = (iter.total ?? 0) > 0;
    const passed = iter.passed ?? 0;
    const total = iter.total ?? 0;
    const passRate = iter.passRate ?? 0;
    return (_jsxs(Box, { children: [statusGlyph(iter.status, iter.patched ? PALETTE.strike : PALETTE.defender), _jsx(Text, { color: PALETTE.dim, children: '  ' }), _jsx(Text, { color: PALETTE.defender, bold: true, children: `i${iterLabel}` }), iter.status === 'running' ? (_jsxs(_Fragment, { children: [_jsx(Text, { color: PALETTE.dim, children: '  ░▒▓█ ' }), _jsx(Text, { color: PALETTE.meta, children: 'generate' })] })) : (_jsxs(_Fragment, { children: [showCompile && (_jsxs(_Fragment, { children: [_jsx(Text, { color: PALETTE.dim, children: '  ' }), _jsx(Text, { color: iter.compileSuccess ? PALETTE.defender : PALETTE.attacker, children: iter.compileSuccess ? '✓' : '✗' })] })), showTests && (_jsxs(_Fragment, { children: [_jsx(Text, { color: PALETTE.dim, children: '  ' }), renderTestDots(passed, total, 6), _jsx(Text, { color: PALETTE.dim, children: ' ' }), _jsx(Text, { color: PALETTE.text, children: `${passed}/${total}` }), _jsx(Text, { color: PALETTE.dim, children: '  ' }), _jsx(Text, { color: passRate >= 1 ? PALETTE.defender : PALETTE.attacker, children: `${(passRate * 100).toFixed(0)}%` })] }))] }))] }));
}
function renderTestDots(passed, total, max = 6) {
    if (total <= 0)
        return _jsx(Text, { color: PALETTE.dim, children: "\u2014" });
    const shown = Math.min(total, max);
    const passedShown = Math.round((passed / total) * shown);
    return (_jsxs(Box, { children: [_jsx(Text, { color: PALETTE.defender, children: GLYPH.testPass.repeat(passedShown) }), _jsx(Text, { color: PALETTE.attacker, children: GLYPH.testFail.repeat(Math.max(0, shown - passedShown)) })] }));
}
// ─── Attacker (right) row — single line per round ─────────────────────────
//   ◆  R1  STRIKE        (or)
//   ◆  R1  clean
//   ▶  R2  probing
function AttackerRow({ round }) {
    const roundLabel = `R${String(round.round).padStart(1, '0')}`;
    const tone = round.landed ? PALETTE.strike : PALETTE.attacker;
    return (_jsxs(Box, { children: [statusGlyph(round.status, tone), _jsx(Text, { color: PALETTE.dim, children: '  ' }), _jsx(Text, { color: tone, bold: true, children: roundLabel }), round.status === 'running' && (_jsx(Text, { color: PALETTE.meta, children: '   probing' })), round.status === 'done' && round.landed === true && (_jsxs(_Fragment, { children: [_jsx(Text, { color: PALETTE.dim, children: '   ⚡ ' }), _jsx(Text, { color: PALETTE.strike, bold: true, children: 'STRIKE' })] })), round.status === 'done' && round.landed === false && (_jsx(Text, { color: PALETTE.meta, children: '   clean' }))] }));
}
// ─── Strike scar (horizontal cross-column line) ─────────────────────────────
// ─── Strike scar — single horizontal scar that NEVER wraps ────────────────
//   ⚡  STRIKE  R1 → i01  ·  WA ──────────────────────────────────────────
//
// Width math: the leading ⚡ glyph and the trailing ⚡ are wide chars
// (2 cells each on most terminals). We compute filler conservatively so
// total cell width ≤ width − 4 (4-cell safety margin).
function StrikeRow({ strike, width, }) {
    const verdict = (strike.failureType ?? 'BREAK').toUpperCase();
    // Tag = "  ⚡  STRIKE  R{n} → i{NN}  ·  {VERDICT}  "
    // Visible cells: 2 leading + 2 (⚡) + 2 + 6 + 2 + 2 + len(R{n}) + 4 +
    //                len(i{NN}) + 4 + 1 + len(verdict) + 2 = roughly 30 + len
    const tagText = `  ⚡  STRIKE  R${strike.round} → i${String((strike.defenderIter ?? 0) + 1).padStart(2, '0')}  ·  ${verdict}  `;
    // Account for the wide ⚡ (visible cell count = string length + 1)
    const tagCells = tagText.length + 1;
    const filler = '─'.repeat(Math.max(0, width - tagCells - 2));
    return (_jsxs(Box, { flexDirection: "column", children: [_jsxs(Box, { children: [_jsx(Text, { color: PALETTE.strike, bold: true, children: tagText }), _jsx(Text, { color: PALETTE.strike, children: filler })] }), strike.failingInputHead && (_jsxs(Box, { marginLeft: 4, children: [_jsx(Text, { color: PALETTE.meta, children: 'input    ' }), _jsx(Text, { color: PALETTE.text, children: fitOneLine(strike.failingInputHead, width - 14) })] })), strike.expectedHead && (_jsxs(Box, { marginLeft: 4, children: [_jsx(Text, { color: PALETTE.meta, children: 'expected ' }), _jsx(Text, { color: PALETTE.defender, children: fitOneLine(strike.expectedHead, width - 14) })] })), strike.actualHead && (_jsxs(Box, { marginLeft: 4, children: [_jsx(Text, { color: PALETTE.meta, children: 'got      ' }), _jsx(Text, { color: PALETTE.attacker, children: fitOneLine(strike.actualHead, width - 14) })] }))] }));
}
function fitOneLine(s, max) {
    const collapsed = s.replace(/\s+/g, ' ').trim();
    if (collapsed.length <= max || max <= 1)
        return collapsed.slice(0, Math.max(0, max));
    return collapsed.slice(0, max - 1) + '…';
}
// ─── Duel container ─────────────────────────────────────────────────────────
export function Duel({ defender, attacker, strikes, width }) {
    // Two columns each gets (width - 4) / 2; floor it. Each column has paddingX=1
    // (consumes 2 cells per column). Dot grid budget = colWidth - 4 (3-cell
    // indent + 1-cell right safety) and "· " is 2 cells per dot.
    const colWidth = Math.floor((width - 4) / 2);
    const dotsPerCol = Math.max(0, Math.floor((colWidth - 4) / 2));
    const gridRow = `${GLYPH.gridDot} `.repeat(dotsPerCol);
    const gap = '    ';
    const hasStrike = strikes.length > 0;
    return (_jsxs(Box, { flexDirection: "column", children: [_jsxs(Box, { children: [_jsxs(Box, { width: colWidth, children: [_jsx(Text, { color: PALETTE.defender, bold: true, children: `     ${spaceCaps('DEFENDER')}` }), _jsx(Text, { color: PALETTE.dim, children: '  · codegen' })] }), _jsx(Text, { children: gap }), _jsxs(Box, { width: colWidth, children: [_jsx(Text, { color: PALETTE.attacker, bold: true, children: `     ${spaceCaps('ATTACKER')}` }), _jsx(Text, { color: PALETTE.dim, children: '  · hacker' })] })] }), _jsxs(Box, { children: [_jsx(Box, { width: colWidth, children: _jsx(Text, { color: PALETTE.grid, children: `   ${gridRow}` }) }), _jsx(Text, { children: gap }), _jsx(Box, { width: colWidth, children: _jsx(Text, { color: PALETTE.grid, children: `   ${gridRow}` }) })] }), _jsxs(Box, { children: [_jsx(Box, { flexDirection: "column", width: colWidth, paddingX: 1, children: defender.length === 0 ? (_jsx(Text, { color: PALETTE.dim, children: '   awaiting first iteration …' })) : (defender.map((iter, idx) => (_jsx(DefenderRow, { iter: iter }, `d-${idx}`)))) }), _jsx(Text, { children: gap }), _jsx(Box, { flexDirection: "column", width: colWidth, paddingX: 1, children: attacker.length === 0 ? (_jsx(Text, { color: PALETTE.dim, children: '   no rounds yet …' })) : (attacker.map((round, idx) => (_jsx(AttackerRow, { round: round }, `a-${idx}`)))) })] }), hasStrike && (_jsx(Box, { flexDirection: "column", marginTop: 1, children: strikes.map((s, i) => (_jsx(StrikeRow, { strike: s, width: width, leftWidth: colWidth, rightWidth: colWidth }, `s-${i}`))) }))] }));
}
//# sourceMappingURL=Duel.js.map