import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Box, Text } from 'ink';
import InkSpinner from 'ink-spinner';
import { PALETTE, GLYPH } from '../theme.js';
const HEADERS = {
    abstract_phase: 'ABSTRACT',
    testgen_phase: 'TESTGEN',
    solver_skill_plan: 'PLAN',
};
function StatusGlyph({ status }) {
    if (status === 'running') {
        return (_jsx(Text, { color: PALETTE.referee, children: _jsx(InkSpinner, { type: "dots" }) }));
    }
    if (status === 'done') {
        return _jsx(Text, { color: PALETTE.referee, children: GLYPH.done });
    }
    return _jsx(Text, { color: PALETTE.dim, children: GLYPH.idle });
}
function ConfidenceBar({ conf }) {
    // Render a single eighth-block for confidence 0..1
    const idx = Math.max(0, Math.min(7, Math.floor(conf * 8)));
    return _jsx(Text, { color: PALETTE.referee, children: GLYPH.barEighths[idx] });
}
function ArenaRow({ item }) {
    const labelText = `${HEADERS[item.key].padEnd(10)}`;
    let detail = _jsx(Text, { color: PALETTE.dim, children: "\u2014" });
    if (item.status === 'running' || item.status === 'pending') {
        detail = _jsx(Text, { color: PALETTE.dim, children: item.status === 'running' ? '…' : '' });
    }
    else if (item.key === 'abstract_phase') {
        const tags = (item.tags ?? []).join(' · ') || '—';
        const conf = item.confidence ?? 0;
        detail = (_jsxs(Box, { children: [_jsx(Text, { color: PALETTE.dim, children: 'tags  ' }), _jsx(Text, { color: PALETTE.text, children: tags }), _jsx(Text, { color: PALETTE.dim, children: '        conf  ' }), _jsx(Text, { color: PALETTE.text, children: `${(conf * 100).toFixed(0)} ` }), _jsx(ConfidenceBar, { conf: conf })] }));
    }
    else if (item.key === 'testgen_phase') {
        const n = item.testCount ?? 0;
        const dots = GLYPH.testPass.repeat(Math.min(n, 12));
        detail = (_jsxs(Box, { children: [_jsx(Text, { color: PALETTE.dim, children: 'oracle  ' }), _jsx(Text, { color: PALETTE.text, children: `${n} cases  ` }), _jsx(Text, { color: PALETTE.referee, children: dots })] }));
    }
    else if (item.key === 'solver_skill_plan') {
        const algo = item.algorithm || '(skill_graph fallback)';
        detail = (_jsxs(Box, { children: [_jsx(Text, { color: PALETTE.dim, children: 'skill_graph → ' }), _jsx(Text, { color: PALETTE.text, children: algo })] }));
    }
    return (_jsxs(Box, { children: [_jsx(Text, { color: PALETTE.text, children: '  ' }), _jsx(StatusGlyph, { status: item.status }), _jsx(Text, { color: PALETTE.dim, children: '   ' }), _jsx(Text, { color: PALETTE.text, bold: true, children: labelText }), detail] }));
}
export function Arena({ arena, width }) {
    // Always render the three slots in canonical order, even if not yet emitted
    const order = [
        'abstract_phase',
        'testgen_phase',
        'solver_skill_plan',
    ];
    const byKey = new Map(arena.map((a) => [a.key, a]));
    const rendered = order.map((k) => byKey.get(k) ?? {
        key: k,
        label: HEADERS[k],
        status: 'pending',
    });
    // Heavy ARENA rule with embedded label
    const label = ' ARENA ';
    const sideLen = Math.max(2, Math.floor((width - label.length) / 2));
    const headerRule = GLYPH.ruleHeavy.repeat(sideLen) +
        label +
        GLYPH.ruleHeavy.repeat(width - sideLen - label.length);
    const footerRule = GLYPH.ruleHeavy.repeat(width);
    return (_jsxs(Box, { flexDirection: "column", marginBottom: 1, children: [_jsx(Text, { color: PALETTE.rule, children: headerRule }), rendered.map((item) => (_jsx(ArenaRow, { item: item }, item.key))), _jsx(Text, { color: PALETTE.rule, children: footerRule })] }));
}
//# sourceMappingURL=Arena.js.map