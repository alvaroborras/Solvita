/**
 * Interactive problem input component.
 *
 * Three sub-modes (switch with Tab / arrow keys):
 *   1. Select from data/problem/ directory
 *   2. Type a file path
 *   3. Paste problem description (multiline; submit with Ctrl+D or Ctrl+Enter)
 *
 * On selection, calls onSubmit(inputFile, description?) so the parent can
 * launch the solver.
 */
import React, { useState, useCallback } from 'react';
import { Box, Text, useInput } from 'ink';
import { useFilePicker } from '../hooks/useFilePicker.js';

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
    // Tab cycles between sub-modes
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
      // Ctrl+D or Ctrl+Enter to submit
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
      {/* Tab bar */}
      <Box marginBottom={1}>
        {tabs.map((t) => (
          <Text
            key={t}
            bold={subMode === t}
            color={subMode === t ? 'cyan' : 'gray'}
            underline={subMode === t}
          >
            {tabLabels[t]}
          </Text>
        ))}
        <Text color="gray">  (Tab to switch)</Text>
      </Box>

      {/* Pick mode */}
      {subMode === 'pick' && (
        <Box flexDirection="column">
          {entries.length === 0 ? (
            <Text color="yellow">  No JSON files found in data/problem/</Text>
          ) : (
            entries.map((entry, i) => (
              <Text
                key={entry.fullPath}
                color={i === selectedIndex ? 'white' : 'gray'}
                bold={i === selectedIndex}
              >
                {i === selectedIndex ? '  ▶ ' : '    '}
                {entry.label}
              </Text>
            ))
          )}
          <Text color="gray" dimColor>
            {'\n  ↑↓ navigate  Enter to solve'}
          </Text>
        </Box>
      )}

      {/* Path mode */}
      {subMode === 'path' && (
        <Box flexDirection="column">
          <Text color="gray">  Path to problem JSON:</Text>
          <Box borderStyle="round" borderColor="cyan" paddingX={1} marginTop={1}>
            <Text color="white">{pathText || ' '}</Text>
            <Text color="cyan">{'█'}</Text>
          </Box>
          <Text color="gray" dimColor>
            {'  Enter to solve'}
          </Text>
        </Box>
      )}

      {/* Paste mode */}
      {subMode === 'paste' && (
        <Box flexDirection="column">
          <Text color="gray">
            {'  Paste problem description below. Press Ctrl+D to submit.'}
          </Text>
          <Box
            borderStyle="round"
            borderColor="cyan"
            paddingX={1}
            marginTop={1}
            flexDirection="column"
          >
            <Text color="white" wrap="wrap">
              {pasteText || ' '}
            </Text>
            <Text color="cyan">{'█'}</Text>
          </Box>
          <Text color="gray" dimColor>
            {'  Ctrl+D to solve'}
          </Text>
        </Box>
      )}
    </Box>
  );
}
