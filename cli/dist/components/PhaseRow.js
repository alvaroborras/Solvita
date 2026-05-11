import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Box, Text } from 'ink';
import InkSpinner from 'ink-spinner';
function SpinnerIcon() {
    return (_jsx(Text, { color: "cyan", children: _jsx(InkSpinner, { type: "dots" }) }));
}
export function PhaseRow({ label, status, detail }) {
    const iconNode = status === 'running' ? (_jsxs(Box, { children: [_jsx(Text, { children: '  ' }), _jsx(SpinnerIcon, {})] })) : status === 'done' ? (_jsx(Text, { color: "green", children: '  ✔' })) : status === 'error' ? (_jsx(Text, { color: "red", children: '  ✖' })) : (_jsx(Text, { color: "gray", children: '  ○' }));
    return (_jsxs(Box, { children: [iconNode, _jsx(Text, { color: status === 'done'
                    ? 'white'
                    : status === 'error'
                        ? 'red'
                        : status === 'running'
                            ? 'cyan'
                            : 'gray', bold: status === 'running', children: `  ${label}` }), detail ? _jsx(Text, { color: "gray", children: `   ${detail}` }) : null] }));
}
//# sourceMappingURL=PhaseRow.js.map