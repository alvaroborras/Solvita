import type { LiveProgress } from '../utils/buildLiveProgress';
import { stageText, useI18n } from '../i18n';

interface LiveProgressPanelProps {
  progress: LiveProgress;
}

function metricValue(value: number | string | null): string {
  if (value === null || value === '') {
    return '—';
  }
  return String(value);
}

export default function LiveProgressPanel({ progress }: LiveProgressPanelProps) {
  const { language, t } = useI18n();
  const stageLabel = progress.stageId ? stageText(language, progress.stageId).title : t('idleStage');

  return (
    <section className="live-progress-panel surface-card">
      <div className="live-progress-panel__head">
        <div>
          <div className="surface-kicker">{t('fineGrainedProgress')}</div>
          <h2 className="surface-title">{progress.currentStepLabel}</h2>
        </div>
        <span className="journey-pill journey-pill--status">{stageLabel}</span>
      </div>

      <p className="live-progress-panel__summary">{progress.currentStepSummary}</p>

      <div className="live-progress-panel__metrics">
        <div className="live-progress-panel__metric">
          <span className="live-progress-panel__metricLabel">{t('iteration')}</span>
          <span className="live-progress-panel__metricValue">{metricValue(progress.metrics.iteration)}</span>
        </div>
        <div className="live-progress-panel__metric">
          <span className="live-progress-panel__metricLabel">{t('visibleTests')}</span>
          <span className="live-progress-panel__metricValue">
            {metricValue(progress.metrics.passed)}/{metricValue(progress.metrics.total)}
          </span>
        </div>
        <div className="live-progress-panel__metric">
          <span className="live-progress-panel__metricLabel">{t('result')}</span>
          <span className="live-progress-panel__metricValue">{metricValue(progress.metrics.resultStatus)}</span>
        </div>
        <div className="live-progress-panel__metric">
          <span className="live-progress-panel__metricLabel">{t('hackRound')}</span>
          <span className="live-progress-panel__metricValue">{metricValue(progress.metrics.hackRound)}</span>
        </div>
      </div>
    </section>
  );
}
