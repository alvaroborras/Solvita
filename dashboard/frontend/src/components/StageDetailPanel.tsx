import { useEffect, useState } from 'react';
import { JourneyStageCard, JourneyTimelineEntry } from '../types/journey';
import { formatStageVisits, stageStatusLabel, useI18n } from '../i18n';

interface StageDetailPanelProps {
  stage: JourneyStageCard | null;
  timelineEntry: JourneyTimelineEntry | null;
}

type DetailTab = 'what' | 'why' | 'evidence';

export default function StageDetailPanel({ stage, timelineEntry }: StageDetailPanelProps) {
  const { language, t } = useI18n();
  const [tab, setTab] = useState<DetailTab>('what');

  useEffect(() => {
    setTab('what');
  }, [stage?.id, timelineEntry?.id]);

  if (!stage) {
    return (
      <section className="detail-panel surface-card">
        <div className="surface-kicker">{t('stageDetail')}</div>
        <h2 className="surface-title">{t('selectStage')}</h2>
        <p className="detail-panel__empty">
          {t('stageDetailEmpty')}
        </p>
      </section>
    );
  }

  const whyLines = timelineEntry?.why.length ? timelineEntry.why : stage.whyNotes;
  const evidenceLines = timelineEntry?.evidence.length ? timelineEntry.evidence : stage.evidence;
  const steps = timelineEntry?.steps.length ? timelineEntry.steps : stage.steps;

  return (
    <section className="detail-panel surface-card">
      <div className="detail-panel__head">
        <div>
          <div className="surface-kicker">{t('stageDetail')}</div>
          <h2 className="surface-title">{stage.title}</h2>
        </div>
        <span className={`journey-pill journey-pill--detail journey-pill--${stage.status}`}>
          {stageStatusLabel(language, stage.status)}
        </span>
      </div>

      <div className="detail-panel__summary">
        <div className="detail-panel__meta">
          <span>{formatStageVisits(language, stage.visits)}</span>
          {stage.latestVisit && <span>{language === 'zh' ? `最新 #${stage.latestVisit}` : `latest #${stage.latestVisit}`}</span>}
        </div>
        <p>{stage.summary}</p>
      </div>

      <div className="detail-tabs">
        {(['what', 'why', 'evidence'] as const).map((nextTab) => (
          <button
            key={nextTab}
            type="button"
            className={`detail-tabs__tab ${tab === nextTab ? 'detail-tabs__tab--active' : ''}`}
            onClick={() => setTab(nextTab)}
          >
            {nextTab === 'what' ? t('what') : nextTab === 'why' ? t('why') : t('evidence')}
          </button>
        ))}
      </div>

      {tab === 'what' && (
        <div className="detail-panel__body">
          <p className="detail-panel__lead">{stage.what}</p>
          {steps.length > 0 && (
            <div className="detail-panel__list">
              {steps.map((step) => (
                <div key={step.id} className={`detail-panel__step detail-panel__step--${step.status}`}>
                  <div className="detail-panel__stepLabel">{step.label}</div>
                  <div className="detail-panel__stepSummary">{step.summary}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === 'why' && (
        <div className="detail-panel__body">
          <div className="detail-panel__list">
            {whyLines.map((line, index) => (
              <div key={`${stage.id}-why-${index}`} className="detail-panel__bullet">
                {line}
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === 'evidence' && (
        <div className="detail-panel__body">
          {evidenceLines.length > 0 ? (
            <div className="detail-panel__list">
              {evidenceLines.map((line, index) => (
                <div key={`${stage.id}-evidence-${index}`} className="detail-panel__bullet">
                  {line}
                </div>
              ))}
            </div>
          ) : (
            <p className="detail-panel__empty">
              {t('noExtraEvidence')}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
