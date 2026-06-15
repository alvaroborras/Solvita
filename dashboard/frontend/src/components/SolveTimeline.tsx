import { JourneyTimelineEntry } from '../types/journey';
import { localizedBeatStatus, useI18n } from '../i18n';

interface SolveTimelineProps {
  entries: JourneyTimelineEntry[];
  progressSeq: number;
  selectedEntryId: string | null;
  mode: 'live' | 'replay' | 'idle';
  onSelect: (entry: JourneyTimelineEntry) => void;
}

function entryProgress(entry: JourneyTimelineEntry, progressSeq: number): 'past' | 'current' | 'future' {
  if (entry.status === 'active' && progressSeq >= entry.startSeq) return 'current';
  if (progressSeq < entry.startSeq) return 'future';
  if (progressSeq >= entry.endSeq) return 'past';
  return 'current';
}

function formatDuration(entry: JourneyTimelineEntry): string {
  const seconds = Math.max(0, Math.round(entry.endedAt - entry.startedAt));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${minutes}m ${remainder}s`;
}

export default function SolveTimeline({
  entries,
  progressSeq,
  selectedEntryId,
  mode,
  onSelect,
}: SolveTimelineProps) {
  const { language, t } = useI18n();
  if (entries.length === 0) {
    return (
      <section className="timeline-shell surface-card">
        <div className="surface-kicker">{t('timeline')}</div>
        <h2 className="surface-title">{t('nothingYet')}</h2>
        <p className="timeline-shell__empty">
          {t('timelineEmpty')}
        </p>
      </section>
    );
  }

  return (
    <section className="timeline-shell surface-card">
      <div className="timeline-shell__head">
        <div>
          <div className="surface-kicker">{t('timeline')}</div>
          <h2 className="surface-title">{t('timelineTitle')}</h2>
        </div>
        <p className="timeline-shell__hint">
          {mode === 'replay'
            ? t('timelineReplayHint')
            : t('timelineLiveHint')}
        </p>
      </div>

      <div className="timeline-list">
        {entries.map((entry, index) => {
          const progress = entryProgress(entry, progressSeq);
          const selected = selectedEntryId === entry.id;
          const timelineIndex = (index + 1).toString().padStart(2, '0');
          return (
            <button
              key={entry.id}
              type="button"
              className={[
                'timeline-card',
                `timeline-card--${entry.status}`,
                `timeline-card--${progress}`,
                selected ? 'timeline-card--selected' : '',
              ].join(' ')}
              aria-pressed={selected}
              onClick={() => onSelect(entry)}
            >
              <div className="timeline-card__rail" />

              <div className="timeline-card__body">
                <div className="timeline-card__top">
                  <div className="timeline-card__titleBlock">
                    <span className="timeline-card__visit">{timelineIndex}</span>
                    <div>
                      <div className="timeline-card__title">{entry.title}</div>
                      <div className="timeline-card__subtitle">{entry.summary}</div>
                    </div>
                  </div>
                  <div className="timeline-card__badges">
                    <span className={`journey-pill journey-pill--timeline journey-pill--${entry.status}`}>
                      {localizedBeatStatus(language, entry.status)}
                    </span>
                    <span className="timeline-card__duration">{formatDuration(entry)}</span>
                  </div>
                </div>

                <div className="timeline-card__meta">
                  <span>{t('stagePass')} #{entry.visit}</span>
                  <span>{entry.steps.length} {entry.steps.length === 1 ? t('substep') : t('substeps')}</span>
                  <span>{entry.evidence.length} {entry.evidence.length === 1 ? t('evidencePoint') : t('evidencePoints')}</span>
                </div>

                {selected && (
                  <div className="timeline-card__expanded">
                    <div className="timeline-card__steps">
                      {entry.steps.map((step) => (
                        <div key={step.id} className={`timeline-step timeline-step--${step.status}`}>
                          <div className="timeline-step__label">{step.label}</div>
                          <div className="timeline-step__summary">{step.summary}</div>
                        </div>
                      ))}
                    </div>

                    {entry.evidence.length > 0 && (
                      <div className="timeline-card__evidence">
                        {entry.evidence.map((line, index) => (
                          <div key={`${entry.id}-evidence-${index}`} className="timeline-card__evidenceItem">
                            {line}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}
