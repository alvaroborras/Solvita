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
// ─── Defender (left) row ────────────────────────────────────────────────────
function DefenderRow({ iter }) {
    const iterLabel = iter.iteration < 0 ? '··' : String(iter.iteration + 1).padStart(2, '0');
    const compileLabel = iter.compileSuccess === undefined
        ? '—'
        : iter.compileSuccess
            ? 'ok'
            : 'fail';
    return (_jsxs(Box, { flexDirection: "column", marginBottom: 1, children: [_jsxs(Box, { children: [statusGlyph(iter.status, PALETTE.defender), _jsx(Text, { color: PALETTE.dim, children: '  ' }), _jsx(Text, { color: PALETTE.defender, bold: true, children: `i${iterLabel}` }), _jsx(Text, { color: PALETTE.dim, children: iter.patched ? '   ← patching' : '' })] }), iter.status === 'done' && (_jsxs(_Fragment, { children: [_jsxs(Box, { children: [_jsx(Text, { color: PALETTE.dim, children: '      compile  ' }), _jsx(Text, { color: iter.compileSuccess ? PALETTE.defender : PALETTE.attacker, children: compileLabel })] }), _jsxs(Box, { children: [_jsx(Text, { color: PALETTE.dim, children: '      tests    ' }), passDots(iter.passed ?? 0, iter.total ?? 0)] })] })), iter.status === 'running' && (_jsxs(Box, { children: [_jsx(Text, { color: PALETTE.dim, children: '      ' }), _jsx(Text, { color: PALETTE.dim, children: "generate \u00B7 \u2591\u2592\u2593\u2588" })] }))] }));
}
// ─── Attacker (right) row ───────────────────────────────────────────────────
function AttackerRow({ round }) {
    const roundLabel = `R${String(round.round).padStart(1, '0')}`;
    return (_jsxs(Box, { flexDirection: "column", marginBottom: 1, children: [_jsxs(Box, { children: [statusGlyph(round.status, round.landed ? PALETTE.strike : PALETTE.attacker), _jsx(Text, { color: PALETTE.dim, children: '  ' }), _jsx(Text, { color: round.landed ? PALETTE.strike : PALETTE.attacker, bold: true, children: roundLabel }), round.status === 'running' && (_jsx(Text, { color: PALETTE.dim, children: '   probing …' }))] }), round.status === 'done' && (_jsxs(Box, { children: [_jsx(Text, { color: PALETTE.dim, children: '      ' }), round.landed ? (_jsx(Text, { color: PALETTE.strike, children: '⚡ landed strike' })) : (_jsx(Text, { color: PALETTE.dim, children: 'all clear' }))] }))] }));
}
// ─── Strike scar (horizontal cross-column line) ─────────────────────────────
function StrikeRow({ strike, width, leftWidth, rightWidth, }) {
    // Render: "  ⚡──── STRIKE round R{n}, vs i{NN}  type=WA ─────"
    // followed by an indented payload block when the backend emitted detail.
    const verdict = strike.failureType?.toUpperCase() || 'BREAK';
    const tag = `  ⚡──── STRIKE round R${strike.round}  vs i${String((strike.defenderIter ?? 0) + 1).padStart(2, '0')}  ·  ${verdict} ────`;
    const filler = '─'.repeat(Math.max(0, width - tag.length - 2));
    // Truncate any field to fit one terminal line
    const fitLine = (s) => s.length > width - 12 ? s.slice(0, width - 13) + '…' : s;
    const inHead = (strike.failingInputHead ?? '').replace(/\s+/g, ' ').trim();
    const expHead = (strike.expectedHead ?? '').replace(/\s+/g, ' ').trim();
    const actHead = (strike.actualHead ?? '').replace(/\s+/g, ' ').trim();
    return (_jsxs(Box, { flexDirection: "column", children: [_jsxs(Box, { children: [_jsx(Text, { color: PALETTE.strike, children: tag }), _jsx(Text, { color: PALETTE.dim, children: filler })] }), inHead && (_jsxs(Box, { marginLeft: 4, children: [_jsx(Text, { color: PALETTE.meta, children: 'input    ' }), _jsx(Text, { color: PALETTE.text, children: fitLine(inHead) })] })), expHead && (_jsxs(Box, { marginLeft: 4, children: [_jsx(Text, { color: PALETTE.meta, children: 'expected ' }), _jsx(Text, { color: PALETTE.defender, children: fitLine(expHead) })] })), actHead && (_jsxs(Box, { marginLeft: 4, children: [_jsx(Text, { color: PALETTE.meta, children: 'got      ' }), _jsx(Text, { color: PALETTE.attacker, children: fitLine(actHead) })] }))] }));
}
// ─── Duel container ─────────────────────────────────────────────────────────
export function Duel({ defender, attacker, strikes, width }) {
    // Title row: DEFENDER · codegen        ATTACKER · hacker
    const colWidth = Math.floor((width - 4) / 2);
    const dot = `${GLYPH.gridDot} `;
    const gridRow = dot.repeat(Math.floor(colWidth / 2));
    const gap = '    ';
    // Determine if there are any strikes to render between specific iters
    // (we render them inline at the bottom of the duel block for now — a future
    // improvement would interleave them at the precise iter boundary)
    const hasStrike = strikes.length > 0;
    return (_jsxs(Box, { flexDirection: "column", children: [_jsxs(Box, { children: [_jsxs(Box, { width: colWidth, children: [_jsx(Text, { color: PALETTE.defender, bold: true, children: `     ${spaceCaps('DEFENDER')}` }), _jsx(Text, { color: PALETTE.dim, children: '  · codegen' })] }), _jsx(Text, { children: gap }), _jsxs(Box, { width: colWidth, children: [_jsx(Text, { color: PALETTE.attacker, bold: true, children: `     ${spaceCaps('ATTACKER')}` }), _jsx(Text, { color: PALETTE.dim, children: '  · hacker' })] })] }), _jsxs(Box, { children: [_jsx(Box, { width: colWidth, children: _jsx(Text, { color: PALETTE.grid, children: `   ${gridRow}` }) }), _jsx(Text, { children: gap }), _jsx(Box, { width: colWidth, children: _jsx(Text, { color: PALETTE.grid, children: `   ${gridRow}` }) })] }), _jsxs(Box, { children: [_jsx(Box, { flexDirection: "column", width: colWidth, paddingX: 1, children: defender.length === 0 ? (_jsx(Text, { color: PALETTE.dim, children: '   awaiting first iteration …' })) : (defender.map((iter, idx) => (_jsx(DefenderRow, { iter: iter }, `d-${idx}`)))) }), _jsx(Text, { children: gap }), _jsx(Box, { flexDirection: "column", width: colWidth, paddingX: 1, children: attacker.length === 0 ? (_jsx(Text, { color: PALETTE.dim, children: '   no rounds yet …' })) : (attacker.map((round, idx) => (_jsx(AttackerRow, { round: round }, `a-${idx}`)))) })] }), hasStrike && (_jsx(Box, { flexDirection: "column", marginTop: 1, children: strikes.map((s, i) => (_jsx(StrikeRow, { strike: s, width: width, leftWidth: colWidth, rightWidth: colWidth }, `s-${i}`))) }))] }));
}
//# sourceMappingURL=Duel.js.map