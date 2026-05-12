import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useEffect, useState } from 'react';
import { Box, Text } from 'ink';
import { PALETTE, GLYPH, LAYOUT, spaceCaps } from '../theme.js';
function formatElapsed(ms) {
    const s = Math.floor(ms / 1000);
    const mm = String(Math.floor(s / 60)).padStart(2, '0');
    const ss = String(s % 60).padStart(2, '0');
    return `t+ ${mm}:${ss}`;
}
function formatTokens(n) {
    if (n >= 1000)
        return `${(n / 1000).toFixed(0)} K`;
    return String(n);
}
function buildSparkline(samples, cols) {
    // Render the *cumulative* token count as a 8-step braille bar column,
    // scaled to local max. For low sample counts pad left with empty.
    if (samples.length === 0)
        return '─'.repeat(cols);
    const max = Math.max(...samples, 1);
    const padded = samples.length < cols
        ? Array(cols - samples.length).fill(0).concat(samples)
        : samples.slice(samples.length - cols);
    return padded
        .map((v) => {
        const idx = Math.max(0, Math.min(7, Math.floor((v / max) * 7)));
        return GLYPH.sparkBars[idx];
    })
        .join('');
}
export function Header({ problemId, modelLabel, startedAt, tokens, tokenSamples, cost, width, platformWarning, }) {
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
    return (_jsxs(Box, { flexDirection: "column", marginBottom: 1, children: [_jsxs(Box, { justifyContent: "space-between", children: [_jsxs(Box, { children: [_jsx(Text, { color: PALETTE.text, bold: true, children: titleSpaced }), _jsx(Text, { color: PALETTE.dim, children: '   ·   ' }), _jsx(Text, { color: PALETTE.meta, children: subtitleSpaced })] }), _jsxs(Box, { children: [_jsx(Text, { color: PALETTE.dim, children: 'tokens ' }), _jsx(Text, { color: PALETTE.defender, children: spark }), _jsxs(Text, { color: PALETTE.text, children: ['  ', formatTokens(tokens)] })] })] }), _jsx(Text, { color: PALETTE.rule, children: GLYPH.ruleLight.repeat(width) }), _jsxs(Box, { justifyContent: "space-between", children: [_jsxs(Box, { children: [_jsx(Text, { color: PALETTE.dim, children: 'problem  ' }), _jsx(Text, { color: PALETTE.text, children: problemId ?? '—' })] }), _jsxs(Box, { children: [modelLabel && _jsx(Text, { color: PALETTE.meta, children: modelLabel }), _jsx(Text, { color: PALETTE.dim, children: '   ' }), _jsx(Text, { color: PALETTE.meta, children: elapsed }), costStr && (_jsxs(_Fragment, { children: [_jsx(Text, { color: PALETTE.dim, children: '   ·   ' }), _jsx(Text, { color: PALETTE.meta, children: costStr })] }))] })] }), platformWarning && (_jsx(Box, { marginTop: 1, children: _jsx(Text, { color: PALETTE.attacker, children: '⚠  Windows: C++ rlimit sandbox unavailable; falling back to subprocess mode.' }) }))] }));
}
//# sourceMappingURL=Header.js.map