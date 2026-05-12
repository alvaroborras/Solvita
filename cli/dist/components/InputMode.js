import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
/**
 * Interactive problem input component.
 *
 * Three sub-modes (switch with Tab / arrow keys):
 *   1. Select from data/problem/ directory
 *   2. Type a file path
 *   3. Paste problem description (multiline; submit with Ctrl+D or Ctrl+Enter)
 *
 * On selection, calls onSubmit(inputFile, description?) so the parent can
 * launch the solver. All colors flow through PALETTE so light/dark themes
 * stay readable.
 */
import { useState } from 'react';
import { Box, Text, useInput } from 'ink';
import { useFilePicker } from '../hooks/useFilePicker.js';
import { PALETTE } from '../theme.js';
export function InputMode({ projectRoot, onSubmit }) {
    const [subMode, setSubMode] = useState('pick');
    const [pathText, setPathText] = useState('');
    const [pasteText, setPasteText] = useState('');
    const { entries, selectedIndex, selectNext, selectPrev, selected } = useFilePicker(projectRoot);
    useInput((input, key) => {
        if (key.tab) {
            setSubMode((m) => (m === 'pick' ? 'path' : m === 'path' ? 'paste' : 'pick'));
            return;
        }
        if (subMode === 'pick') {
            if (key.upArrow)
                selectPrev();
            else if (key.downArrow)
                selectNext();
            else if (key.return && selected)
                onSubmit(selected.fullPath);
            return;
        }
        if (subMode === 'path') {
            if (key.return) {
                if (pathText.trim())
                    onSubmit(pathText.trim());
                return;
            }
            if (key.backspace || key.delete) {
                setPathText((t) => t.slice(0, -1));
            }
            else if (input && !key.ctrl && !key.meta) {
                setPathText((t) => t + input);
            }
            return;
        }
        if (subMode === 'paste') {
            if ((key.ctrl && input === 'd') || (key.ctrl && key.return)) {
                if (pasteText.trim())
                    onSubmit('', pasteText.trim());
                return;
            }
            if (key.return) {
                setPasteText((t) => t + '\n');
            }
            else if (key.backspace || key.delete) {
                setPasteText((t) => t.slice(0, -1));
            }
            else if (input && !key.ctrl && !key.meta) {
                setPasteText((t) => t + input);
            }
        }
    });
    const tabs = ['pick', 'path', 'paste'];
    const tabLabels = {
        pick: ' Select problem file ',
        path: ' Enter file path     ',
        paste: ' Paste description   ',
    };
    return (_jsxs(Box, { flexDirection: "column", paddingX: 2, paddingY: 1, children: [_jsxs(Box, { marginBottom: 1, children: [tabs.map((t) => (_jsx(Text, { bold: subMode === t, color: subMode === t ? PALETTE.defender : PALETTE.meta, underline: subMode === t, children: tabLabels[t] }, t))), _jsx(Text, { color: PALETTE.meta, children: '  (Tab to switch)' })] }), subMode === 'pick' && (_jsxs(Box, { flexDirection: "column", children: [entries.length === 0 ? (_jsx(Text, { color: PALETTE.attacker, children: '  No JSON files found in data/problem/' })) : (entries.map((entry, i) => (_jsxs(Text, { color: i === selectedIndex ? PALETTE.text : PALETTE.meta, bold: i === selectedIndex, children: [i === selectedIndex ? '  ▶ ' : '    ', entry.label] }, entry.fullPath)))), _jsx(Text, { color: PALETTE.meta, children: '\n  ↑↓ navigate  Enter to solve' })] })), subMode === 'path' && (_jsxs(Box, { flexDirection: "column", children: [_jsx(Text, { color: PALETTE.meta, children: '  Path to problem JSON:' }), _jsxs(Box, { borderStyle: "round", borderColor: PALETTE.defender, paddingX: 1, marginTop: 1, children: [_jsx(Text, { color: PALETTE.text, children: pathText || ' ' }), _jsx(Text, { color: PALETTE.defender, children: '█' })] }), _jsx(Text, { color: PALETTE.meta, children: '  Enter to solve' })] })), subMode === 'paste' && (_jsxs(Box, { flexDirection: "column", children: [_jsx(Text, { color: PALETTE.meta, children: '  Paste problem description below. Press Ctrl+D to submit.' }), _jsxs(Box, { borderStyle: "round", borderColor: PALETTE.defender, paddingX: 1, marginTop: 1, flexDirection: "column", children: [_jsx(Text, { color: PALETTE.text, wrap: "wrap", children: pasteText || ' ' }), _jsx(Text, { color: PALETTE.defender, children: '█' })] }), _jsx(Text, { color: PALETTE.meta, children: '  Ctrl+D to solve' })] }))] }));
}
//# sourceMappingURL=InputMode.js.map