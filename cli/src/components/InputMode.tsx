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
import React, { useState } from 'react';
import { Box, Text, useInput } from 'ink';
import { useFilePicker } from '../hooks/useFilePicker.js';
import { PALETTE } from '../theme.js';

type SubMode = 'pick' | 'path' | 'paste';

interface InputModeProps {
  projectRoot: string;
  onSubmit: (inputFile: string, description?: string) => void;
}

export function InputMode({ projectRoot, onSubmit }: InputModeProps) {
  const [subMode, setSubMode] = useState<SubMode>('pick');
  const [pathText, setPathText] = useState('');
  const [pasteText, setPasteText] = useState('');
  const { entries, selectedIndex, selectNext, selectPrev, selected } =
    useFilePicker(projectRoot);

  useInput((input, key) => {
    if (key.tab) {
      setSubMode((m) => (m === 'pick' ? 'path' : m === 'path' ? 'paste' : 'pick'));
      return;
    }

    if (subMode === 'pick') {
      if (key.upArrow) selectPrev();
      else if (key.downArrow) selectNext();
      else if (key.return && selected) onSubmit(selected.fullPath);
      return;
    }

    if (subMode === 'path') {
      if (key.return) {
        if (pathText.trim()) onSubmit(pathText.trim());
        return;
      }
      if (key.backspace || key.delete) {
        setPathText((t) => t.slice(0, -1));
      } else if (input && !key.ctrl && !key.meta) {
        setPathText((t) => t + input);
      }
      return;
    }

    if (subMode === 'paste') {
      if ((key.ctrl && input === 'd') || (key.ctrl && key.return)) {
        if (pasteText.trim()) onSubmit('', pasteText.trim());
        return;
      }
      if (key.return) {
        setPasteText((t) => t + '\n');
      } else if (key.backspace || key.delete) {
        setPasteText((t) => t.slice(0, -1));
      } else if (input && !key.ctrl && !key.meta) {
        setPasteText((t) => t + input);
      }
    }
  });

  const tabs: SubMode[] = ['pick', 'path', 'paste'];
  const tabLabels: Record<SubMode, string> = {
    pick: ' Select problem file ',
    path: ' Enter file path     ',
    paste: ' Paste description   ',
  };

  return (
    <Box flexDirection="column" paddingX={2} paddingY={1}>
      {/* Tab bar — active tab uses defender accent so it's the only color
          competing with body text; others are neutral meta gray */}
      <Box marginBottom={1}>
        {tabs.map((t) => (
          <Text
            key={t}
            bold={subMode === t}
            color={subMode === t ? PALETTE.defender : PALETTE.meta}
            underline={subMode === t}
          >
            {tabLabels[t]}
          </Text>
        ))}
        <Text color={PALETTE.meta}>{'  (Tab to switch)'}</Text>
      </Box>

      {/* Pick mode */}
      {subMode === 'pick' && (
        <Box flexDirection="column">
          {entries.length === 0 ? (
            <Text color={PALETTE.attacker}>{'  No JSON files found in data/problem/'}</Text>
          ) : (
            entries.map((entry, i) => (
              <Text
                key={entry.fullPath}
                color={i === selectedIndex ? PALETTE.text : PALETTE.meta}
                bold={i === selectedIndex}
              >
                {i === selectedIndex ? '  ▶ ' : '    '}
                {entry.label}
              </Text>
            ))
          )}
          <Text color={PALETTE.meta}>
            {'\n  ↑↓ navigate  Enter to solve'}
          </Text>
        </Box>
      )}

      {/* Path mode */}
      {subMode === 'path' && (
        <Box flexDirection="column">
          <Text color={PALETTE.meta}>{'  Path to problem JSON:'}</Text>
          <Box borderStyle="round" borderColor={PALETTE.defender} paddingX={1} marginTop={1}>
            <Text color={PALETTE.text}>{pathText || ' '}</Text>
            <Text color={PALETTE.defender}>{'█'}</Text>
          </Box>
          <Text color={PALETTE.meta}>
            {'  Enter to solve'}
          </Text>
        </Box>
      )}

      {/* Paste mode */}
      {subMode === 'paste' && (
        <Box flexDirection="column">
          <Text color={PALETTE.meta}>
            {'  Paste problem description below. Press Ctrl+D to submit.'}
          </Text>
          <Box
            borderStyle="round"
            borderColor={PALETTE.defender}
            paddingX={1}
            marginTop={1}
            flexDirection="column"
          >
            <Text color={PALETTE.text} wrap="wrap">
              {pasteText || ' '}
            </Text>
            <Text color={PALETTE.defender}>{'█'}</Text>
          </Box>
          <Text color={PALETTE.meta}>
            {'  Ctrl+D to solve'}
          </Text>
        </Box>
      )}
    </Box>
  );
}
