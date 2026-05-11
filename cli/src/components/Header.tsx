import React from 'react';
import { Box, Text } from 'ink';

interface HeaderProps {
  subtitle?: string;
  platformWarning?: boolean;
}

const TAGLINE = 'Intelligent Competitive Programming Agent';
const WIDTH = 58;
const INNER = WIDTH - 4; // space inside │  …  │

function pad(s: string): string {
  return s.length >= INNER ? s.slice(0, INNER) : s + ' '.repeat(INNER - s.length);
}

export function Header({ subtitle, platformWarning }: HeaderProps) {
  const title = subtitle ? `Solvita  —  ${subtitle}` : 'Solvita';
  const top = `╭${'─'.repeat(WIDTH - 2)}╮`;
  const bot = `╰${'─'.repeat(WIDTH - 2)}╯`;

  return (
    <Box flexDirection="column" marginBottom={1}>
      <Text bold color="cyan">
        {top}
      </Text>
      <Text bold color="cyan">
        {'│  '}
        <Text bold color="white">
          {pad(title)}
        </Text>
        {'│'}
      </Text>
      <Text bold color="cyan">
        {'│  '}
        <Text color="gray">
          {pad(TAGLINE)}
        </Text>
        {'│'}
      </Text>
      <Text bold color="cyan">
        {bot}
      </Text>
      {platformWarning && (
        <Box marginTop={1}>
          <Text color="yellow">
            {'  ⚠  Windows detected: C++ rlimit sandbox unavailable. Compilation uses basic subprocess mode.'}
          </Text>
        </Box>
      )}
    </Box>
  );
}
