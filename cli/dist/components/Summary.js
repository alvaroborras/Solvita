import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Box, Text } from 'ink';
const WIDTH = 58;
export function Summary({ event, solutionPath }) {
    const success = event.status === 'success' || event.pass_rate === 1.0;
    const color = success ? 'green' : 'yellow';
    const icon = success ? '✔ Solved!' : '✖ Incomplete';
    const passStr = event.total > 0
        ? `${event.passed}/${event.total}  ${(event.pass_rate * 100).toFixed(0)}%`
        : 'no tests';
    const file = solutionPath ?? 'solution.cpp';
    const meta = `${passStr}  │  ${event.iterations} iter  │  ${event.llm_calls} LLM calls`;
    const inner = `${icon}  ${file}  │  ${meta}`;
    return (_jsxs(Box, { flexDirection: "column", marginTop: 1, children: [_jsx(Text, { bold: true, color: color, children: `╭${'─'.repeat(WIDTH - 2)}╮` }), _jsx(Text, { bold: true, color: color, children: `│  ${inner.slice(0, WIDTH - 4).padEnd(WIDTH - 4)}│` }), _jsx(Text, { bold: true, color: color, children: `╰${'─'.repeat(WIDTH - 2)}╯` }), _jsx(Box, { marginTop: 1, children: _jsx(Text, { color: "gray", children: `  Tokens: ${event.prompt_tokens} prompt + ${event.completion_tokens} completion` }) })] }));
}
//# sourceMappingURL=Summary.js.map