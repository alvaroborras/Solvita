import React from 'react';
import { Box, Text } from 'ink';
import InkSpinner from 'ink-spinner';
import type { PhaseStatus } from '../types.js';

interface PhaseRowProps {
  label: string;
  status: PhaseStatus;
  detail?: string;
}

function SpinnerIcon() {
  return (
    <Text color="cyan">
      <InkSpinner type="dots" />
    </Text>
  );
}

export function PhaseRow({ label, status, detail }: PhaseRowProps) {
  const iconNode =
    status === 'running' ? (
      <Box>
        <Text>{'  '}</Text>
        <SpinnerIcon />
      </Box>
    ) : status === 'done' ? (
      <Text color="green">{'  ✔'}</Text>
    ) : status === 'error' ? (
      <Text color="red">{'  ✖'}</Text>
    ) : (
      <Text color="gray">{'  ○'}</Text>
    );

  return (
    <Box>
      {iconNode}
      <Text
        color={
          status === 'done'
            ? 'white'
            : status === 'error'
              ? 'red'
              : status === 'running'
                ? 'cyan'
                : 'gray'
        }
        bold={status === 'running'}
      >
        {`  ${label}`}
      </Text>
      {detail ? <Text color="gray">{`   ${detail}`}</Text> : null}
    </Box>
  );
}
