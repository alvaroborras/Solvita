import { JourneyStageCard, JourneyStatusStrip } from '../types/journey';
import { useI18n } from '../i18n';

interface LiveStatusStripProps {
  status: JourneyStatusStrip;
  currentStage: JourneyStageCard | null;
  mode: 'live' | 'replay' | 'idle';
  replayCursor?: number;
  replayTotal?: number;
}

export default function LiveStatusStrip({
  status,
  currentStage,
  mode,
  replayCursor = 0,
  replayTotal = 0,
}: LiveStatusStripProps) {
  const { t } = useI18n();
  const statusLabel = mode === 'replay'
    ? `${replayCursor}/${replayTotal} ${t('replayEvents')}`
    : currentStage
      ? `${t('stagePrefix')} ${currentStage.title}`
      : t('stageWaiting');

  return (
    <section className="live-strip surface-card">
      <div className="live-strip__left">
        <div className="surface-kicker">{t('journeyStatus')}</div>
        <div className="live-strip__headlineRow">
          <span className={`journey-pill journey-pill--status journey-pill--mode-${mode}`}>{status.overallStatus}</span>
          <span className="live-strip__stage">{statusLabel}</span>
        </div>
        <h3 className="live-strip__headline">{status.headline}</h3>
        <p className="live-strip__detail">{status.detail}</p>
      </div>

      <div className="live-strip__next">
        <div className="surface-kicker">{t('nextLikelyMove')}</div>
        <p>{status.nextHint}</p>
      </div>
    </section>
  );
}
