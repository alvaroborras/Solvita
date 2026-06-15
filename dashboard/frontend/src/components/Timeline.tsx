import { AlgoPilotEvent } from '../types/events';

interface TimelineProps {
  events: AlgoPilotEvent[];
  cursor: number;
  onSeek: (index: number) => void;
}

const typeColors: Record<string, string> = {
  solve_start: 'var(--color-accent-blue)',
  phase_start: 'var(--color-accent-purple)',
  phase_done: 'var(--color-accent-green)',
  node_enter: 'var(--color-text-muted)',
  node_exit: 'var(--color-text-secondary)',
  token_sample: 'var(--color-accent-amber)',
  final: 'var(--color-accent-green)',
  error: 'var(--color-accent-red)',
};

export default function Timeline({ events, cursor, onSeek }: TimelineProps) {
  if (events.length === 0) return null;

  return (
    <div className="timeline">
      <div
        className="timeline__track"
        onClick={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const pct = (e.clientX - rect.left) / rect.width;
          onSeek(Math.round(pct * events.length));
        }}
      >
        <div className="timeline__progress" style={{ width: `${(cursor / events.length) * 100}%` }} />
        <div className="timeline__cursor" style={{ left: `${(cursor / events.length) * 100}%` }} />
        {events.map((ev, i) => (
          <div
            key={i}
            className="timeline__dot"
            style={{
              left: `${(i / events.length) * 100}%`,
              background: typeColors[ev.type] || 'var(--color-text-muted)',
              opacity: i < cursor ? 1 : 0.25,
            }}
          />
        ))}
      </div>
      <div className="timeline__info">
        <span>{cursor} / {events.length}</span>
        <span className="timeline__event-type">{events[cursor - 1]?.type || '—'}</span>
      </div>

      <style>{`
        .timeline {
          padding: var(--space-sm) var(--space-xl);
        }
        .timeline__track {
          position: relative;
          height: 28px;
          background: var(--color-bg-glass);
          border: 1px solid var(--color-border-subtle);
          border-radius: var(--radius-md);
          cursor: pointer;
          overflow: hidden;
        }
        .timeline__progress {
          position: absolute;
          top: 0; bottom: 0; left: 0;
          background: rgba(0, 112, 243, 0.08);
          border-radius: var(--radius-md);
          transition: width 0.1s linear;
        }
        .timeline__cursor {
          position: absolute;
          top: 2px; bottom: 2px;
          width: 3px;
          background: var(--color-text-primary);
          border-radius: 2px;
          z-index: 3;
          transition: left 0.1s linear;
          box-shadow: 0 0 6px rgba(255,255,255,0.3);
        }
        .timeline__dot {
          position: absolute;
          top: 50%;
          transform: translateY(-50%);
          width: 4px;
          height: 4px;
          border-radius: 50%;
          transition: opacity var(--transition-fast);
          z-index: 1;
        }
        .timeline__info {
          display: flex;
          justify-content: space-between;
          margin-top: var(--space-xs);
          font-size: var(--font-size-xs);
          color: var(--color-text-muted);
          font-family: var(--font-mono);
        }
        .timeline__event-type {
          color: var(--color-text-secondary);
        }
      `}</style>
    </div>
  );
}
