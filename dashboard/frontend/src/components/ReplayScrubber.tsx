import { JourneyTimelineEntry } from '../types/journey';
import { useI18n } from '../i18n';

interface ReplayScrubberProps {
  entries: JourneyTimelineEntry[];
  cursor: number;
  total: number;
  selectedEntryId: string | null;
  onSeek: (index: number) => void;
}

function clampPercent(value: number): number {
  return Math.min(100, Math.max(0, value));
}

export default function ReplayScrubber({
  entries,
  cursor,
  total,
  selectedEntryId,
  onSeek,
}: ReplayScrubberProps) {
  const { t } = useI18n();
  if (total <= 0) return null;

  const progressPercent = clampPercent((cursor / total) * 100);

  return (
    <section className="replay-scrubber surface-card">
      <div className="replay-scrubber__head">
        <div>
          <div className="surface-kicker">{t('replayProgress')}</div>
          <h3 className="replay-scrubber__title">{t('replayScrubTitle')}</h3>
        </div>
        <div className="replay-scrubber__meta">
          <span>{cursor}/{total} {t('events')}</span>
          <span>{Math.round(progressPercent)}%</span>
        </div>
      </div>

      <div
        className="replay-scrubber__track"
        onClick={(event) => {
          const rect = event.currentTarget.getBoundingClientRect();
          const pct = (event.clientX - rect.left) / rect.width;
          onSeek(Math.round(Math.max(0, Math.min(1, pct)) * total));
        }}
      >
        <div className="replay-scrubber__fill" style={{ width: `${progressPercent}%` }} />
        <div className="replay-scrubber__cursor" style={{ left: `${progressPercent}%` }} />
        {entries.map((entry) => {
          const left = clampPercent(((entry.endSeq + 1) / total) * 100);
          const visited = cursor >= entry.endSeq + 1;
          return (
            <button
              key={entry.id}
              type="button"
              className={[
                'replay-scrubber__marker',
                visited ? 'replay-scrubber__marker--visited' : '',
                selectedEntryId === entry.id ? 'replay-scrubber__marker--selected' : '',
              ].join(' ')}
              style={{ left: `${left}%` }}
              onClick={(clickEvent) => {
                clickEvent.stopPropagation();
                onSeek(entry.endSeq + 1);
              }}
              title={`${entry.title} (#${entry.visit})`}
            />
          );
        })}
      </div>

      <div className="replay-scrubber__stages">
        {entries.map((entry) => (
          <button
            key={`${entry.id}-chip`}
            type="button"
            className={[
              'replay-scrubber__chip',
              selectedEntryId === entry.id ? 'replay-scrubber__chip--selected' : '',
            ].join(' ')}
            onClick={() => onSeek(entry.endSeq + 1)}
          >
            <span>{entry.title}</span>
            <span className="replay-scrubber__chipVisit">#{entry.visit}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
