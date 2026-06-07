import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import SessionBar from './SessionBar';

describe('SessionBar', () => {
  it('shows run metadata and exposes recovery actions', async () => {
    const user = userEvent.setup();
    const onReconnect = vi.fn();
    const onResumeLatest = vi.fn();

    render(
      <SessionBar
        problemName="pair sum"
        runId="run-123456"
        mode="live"
        wsStatus="reconnecting"
        hydrationStatus="ready"
        onReconnect={onReconnect}
        onResumeLatest={onResumeLatest}
      />,
    );

    expect(screen.getByText(/AlgoPilot Session/i)).toBeInTheDocument();
    expect(screen.getByText(/run-123456/i)).toBeInTheDocument();
    expect(screen.getAllByText(/live/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/reconnecting/i).length).toBeGreaterThan(0);

    await user.click(screen.getByRole('button', { name: /reconnect/i }));
    await user.click(screen.getByRole('button', { name: /resume latest algopilot run/i }));

    expect(onReconnect).toHaveBeenCalledTimes(1);
    expect(onResumeLatest).toHaveBeenCalledTimes(1);
  });

  it('shows and wires an interrupt action for live runs', async () => {
    const user = userEvent.setup();
    const onInterrupt = vi.fn();

    render(
      <SessionBar
        problemName="pair sum"
        runId="run-live"
        mode="live"
        wsStatus="connected"
        hydrationStatus="ready"
        canInterrupt
        interruptPending={false}
        onInterrupt={onInterrupt}
        onReconnect={vi.fn()}
        onResumeLatest={vi.fn()}
      />,
    );

    await user.click(screen.getByRole('button', { name: /interrupt/i }));
    expect(onInterrupt).toHaveBeenCalledTimes(1);
  });
});
