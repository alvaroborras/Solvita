import { Fragment } from 'react';

import { JourneyStageCard, JourneyStageId } from '../types/journey';
import { formatStageVisits, stageStatusLabel, useI18n } from '../i18n';

interface SolveJourneyMapProps {
  stages: JourneyStageCard[];
  activeStageId: JourneyStageId | null;
  selectedStageId: JourneyStageId | null;
  mode: 'live' | 'replay' | 'idle';
  onSelect: (stageId: JourneyStageId) => void;
}

export default function SolveJourneyMap({
  stages,
  activeStageId,
  selectedStageId,
  mode,
  onSelect,
}: SolveJourneyMapProps) {
  const { language, t } = useI18n();

  return (
    <section className="journey-section surface-card">
      <div className="journey-section__head">
        <div>
          <div className="surface-kicker">{t('solveJourney')}</div>
          <h2 className="surface-title">{t('solveJourneyTitle')}</h2>
        </div>
        <p className="journey-section__lede">
          {mode === 'replay'
            ? t('solveJourneyReplayLede')
            : t('solveJourneyLiveLede')}
        </p>
      </div>

      <div className="journey-map">
        {stages.map((stage, index) => {
          const isSelected = selectedStageId === stage.id;
          const isActive = activeStageId === stage.id;
          return (
            <Fragment key={stage.id}>
              <button
                type="button"
                className={[
                  'journey-stage',
                  `journey-stage--${stage.status}`,
                  isSelected ? 'journey-stage--selected' : '',
                  isActive ? 'journey-stage--live' : '',
                ].join(' ')}
                aria-pressed={isSelected}
                onClick={() => onSelect(stage.id)}
              >
                <div className="journey-stage__top">
                  <span className="journey-stage__badge">{stage.badge}</span>
                  <span className={`journey-pill journey-pill--${stage.status}`}>
                    {stageStatusLabel(language, stage.status)}
                  </span>
                </div>
                <div className="journey-stage__title" title={stage.title}>{stage.title}</div>
                <div className="journey-stage__summary" title={stage.summary}>{stage.summary}</div>
                <div className="journey-stage__meta">
                  {formatStageVisits(language, stage.visits)}
                </div>
              </button>

              {index < stages.length - 1 && (
                <div className={`journey-map__connector journey-map__connector--${stage.status}`} aria-hidden="true" />
              )}
            </Fragment>
          );
        })}
      </div>
    </section>
  );
}
