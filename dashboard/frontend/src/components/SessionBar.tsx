interface SessionBarProps {
  problemName: string;
  runId: string | null;
  mode: 'idle' | 'live' | 'replay';
  wsStatus: string;
  hydrationStatus: string;
  canInterrupt?: boolean;
  interruptPending?: boolean;
  onInterrupt?: () => void;
  onReconnect: () => void;
  onResumeLatest: () => void;
}

function recoveryLabel(hydrationStatus: string): string {
  switch (hydrationStatus) {
    case 'restoring':
      return 'Restoring saved session';
    case 'ready':
      return 'Session hydrated';
    case 'missing':
      return 'Saved run missing';
    case 'error':
      return 'Recovery failed';
    default:
      return 'Waiting for a run';
  }
}

export default function SessionBar({
  problemName,
  runId,
  mode,
  wsStatus,
  hydrationStatus,
  canInterrupt = false,
  interruptPending = false,
  onInterrupt,
  onReconnect,
  onResumeLatest,
}: SessionBarProps) {
  const canReconnect = mode === 'live' && runId !== null && wsStatus !== 'connected';

  return (
    <section className="session-bar surface-card">
      <div className="session-bar__identity">
        <div className="surface-kicker">AlgoPilot Session</div>
        <h1 className="surface-title">{problemName || 'No active run'}</h1>
        <p className="session-bar__meta">
          {runId ? `run ${runId}` : 'idle'} · {mode} · {wsStatus} · {recoveryLabel(hydrationStatus)}
        </p>
      </div>

      <div className="session-bar__chips">
        <span className={`journey-pill journey-pill--mode journey-pill--mode-${mode}`}>{mode}</span>
        <span className={`journey-pill journey-pill--session journey-pill--session-${wsStatus}`}>{wsStatus}</span>
        <span className={`journey-pill journey-pill--session journey-pill--hydration-${hydrationStatus}`}>
          {hydrationStatus}
        </span>
      </div>

      <div className="session-bar__actions">
        {canInterrupt && (
          <button
            type="button"
            className="session-bar__button session-bar__button--danger"
            disabled={interruptPending}
            onClick={onInterrupt}
          >
            {interruptPending ? 'Interrupting...' : 'Interrupt'}
          </button>
        )}
        <button
          type="button"
          className="session-bar__button"
          disabled={!canReconnect}
          onClick={onReconnect}
        >
          Reconnect
        </button>
        <button
          type="button"
          className="session-bar__button session-bar__button--secondary"
          disabled={hydrationStatus === 'restoring'}
          onClick={onResumeLatest}
        >
          Resume Latest AlgoPilot Run
        </button>
      </div>
    </section>
  );
}
