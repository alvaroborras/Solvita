import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Box, Text } from 'ink';
const TAGLINE = 'Intelligent Competitive Programming Agent';
const WIDTH = 58;
const INNER = WIDTH - 4; // space inside │  …  │
function pad(s) {
    return s.length >= INNER ? s.slice(0, INNER) : s + ' '.repeat(INNER - s.length);
}
export function Header({ subtitle, platformWarning }) {
    const title = subtitle ? `Solvita  —  ${subtitle}` : 'Solvita';
    const top = `╭${'─'.repeat(WIDTH - 2)}╮`;
    const bot = `╰${'─'.repeat(WIDTH - 2)}╯`;
    return (_jsxs(Box, { flexDirection: "column", marginBottom: 1, children: [_jsx(Text, { bold: true, color: "cyan", children: top }), _jsxs(Text, { bold: true, color: "cyan", children: ['│  ', _jsx(Text, { bold: true, color: "white", children: pad(title) }), '│'] }), _jsxs(Text, { bold: true, color: "cyan", children: ['│  ', _jsx(Text, { color: "gray", children: pad(TAGLINE) }), '│'] }), _jsx(Text, { bold: true, color: "cyan", children: bot }), platformWarning && (_jsx(Box, { marginTop: 1, children: _jsx(Text, { color: "yellow", children: '  ⚠  Windows detected: C++ rlimit sandbox unavailable. Compilation uses basic subprocess mode.' }) }))] }));
}
//# sourceMappingURL=Header.js.map