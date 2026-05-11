import React from 'react';
import { Box, Text } from 'ink';
import type { FinalEvent } from '../types.js';

interface SummaryProps {
  event: FinalEvent;
  solutionPath: string | null;
}

const WIDTH = 58;

export function Summary({ event, solutionPath }: SummaryProps) {
  const success = event.status === 'success' || event.pass_rate === 1.0;
  const color = success ? 'green' : 'yellow';
  const icon = success ? '✔ Solved!' : '✖ Incomplete';
  const passStr =
    event.total > 0
      ? `${event.passed}/${event.total}  ${(event.pass_rate * 100).toFixed(0)}%`
      : 'no tests';
  const file = solutionPath ?? 'solution.cpp';
  const meta = `${passStr}  │  ${event.iterations} iter  │  ${event.llm_calls} LLM calls`;
  const inner = `${icon}  ${file}  │  ${meta}`;

  return (
    <Box flexDirection="column" marginTop={1}>
      <Text bold color={color}>
        {`╭${'─'.repeat(WIDTH - 2)}╮`}
      </Text>
      <Text bold color={color}>
        {`│  ${inner.slice(0, WIDTH - 4).padEnd(WIDTH - 4)}│`}
      </Text>
      <Text bold color={color}>
        {`╰${'─'.repeat(WIDTH - 2)}╯`}
      </Text>
      <Box marginTop={1}>
        <Text color="gray">
          {`  Tokens: ${event.prompt_tokens} prompt + ${event.completion_tokens} completion`}
        </Text>
      </Box>
    </Box>
  );
}
