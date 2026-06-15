import { localizeDashboardText, useI18n } from '../i18n';

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

function recoveryLabel(hydrationStatus: string, t: ReturnType<typeof useI18n>['t']): string {
  switch (hydrationStatus) {
    case 'restoring':
      return t('restoringSavedSession');
    case 'ready':
      return t('sessionHydrated');
    case 'missing':
      return t('savedRunMissing');
    case 'error':
      return t('recoveryFailed');
    default:
      return t('waitingForRun');
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
  const { language, t } = useI18n();
  const canReconnect = mode === 'live' && runId !== null && wsStatus !== 'connected';
  const modeLabel = localizeDashboardText(language, mode);
  const wsStatusLabel = localizeDashboardText(language, wsStatus);
  const hydrationStatusLabel = localizeDashboardText(language, hydrationStatus);

  return (
    <section className="session-bar surface-card">
      <div className="session-bar__identity">
        <div className="surface-kicker">{t('algoPilotSession')}</div>
        <h1 className="surface-title">{problemName || t('noActiveRun')}</h1>
        <p className="session-bar__meta">
          {runId ? `run ${runId}` : t('idle')} · {modeLabel} · {wsStatusLabel} · {recoveryLabel(hydrationStatus, t)}
        </p>
      </div>

      <div className="session-bar__chips">
        <span className={`journey-pill journey-pill--mode journey-pill--mode-${mode}`}>{modeLabel}</span>
        <span className={`journey-pill journey-pill--session journey-pill--session-${wsStatus}`}>{wsStatusLabel}</span>
        <span className={`journey-pill journey-pill--session journey-pill--hydration-${hydrationStatus}`}>
          {hydrationStatusLabel}
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
            {interruptPending ? t('interrupting') : t('interrupt')}
          </button>
        )}
        <button
          type="button"
          className="session-bar__button"
          disabled={!canReconnect}
          onClick={onReconnect}
        >
          {t('reconnect')}
        </button>
        <button
          type="button"
          className="session-bar__button session-bar__button--secondary"
          disabled={hydrationStatus === 'restoring'}
          onClick={onResumeLatest}
        >
          {t('resumeLatestRun')}
        </button>
      </div>
    </section>
  );
}
