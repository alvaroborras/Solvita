import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Box, Text } from 'ink';
// @ts-ignore — ink-big-text has no types shipped
import BigText from 'ink-big-text';
import { PALETTE, GLYPH } from '../theme.js';
function formatDuration(ms) {
    const s = Math.floor(ms / 1000);
    const mm = String(Math.floor(s / 60)).padStart(2, '0');
    const ss = String(s % 60).padStart(2, '0');
    return `${mm}:${ss}`;
}
function estimateCost(prompt, completion) {
    // very rough: gpt-5.5 indicative pricing — adjust to your provider
    // input  $5  / 1M tok
    // output $15 / 1M tok
    return (prompt * 5 + completion * 15) / 1_000_000;
}
export function Verdict({ event, solutionPath, startedAt, width }) {
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
    return (_jsxs(Box, { flexDirection: "column", marginTop: 1, children: [_jsx(Text, { color: PALETTE.rule, children: rule }), _jsx(Box, { justifyContent: "center", marginY: 0, children: _jsx(BigText, { text: wordingMain, font: verdictFont, colors: [color] }) }), _jsx(Box, { justifyContent: "center", children: _jsx(Text, { color: PALETTE.meta, children: dossier }) }), solutionPath && (_jsx(Box, { justifyContent: "center", marginTop: 1, children: _jsx(Text, { color: PALETTE.dim, children: solutionPath }) }))] }));
}
function formatTokens(n) {
    if (n >= 1000)
        return `${(n / 1000).toFixed(0)} K`;
    return String(n);
}
//# sourceMappingURL=Verdict.js.map