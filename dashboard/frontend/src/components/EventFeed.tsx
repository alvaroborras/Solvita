import { useRef, useEffect } from 'react';
import { AlgoPilotEvent } from '../types/events';

interface EventFeedProps {
  events: AlgoPilotEvent[];
}

const typeConfig: Record<string, { icon: string; color: string }> = {
  solve_start: { icon: '▶', color: 'var(--color-accent-blue)' },
  phase_start: { icon: '◆', color: 'var(--color-accent-purple)' },
  phase_done: { icon: '✓', color: 'var(--color-accent-green)' },
  node_enter: { icon: '→', color: 'var(--color-text-secondary)' },
  node_exit: { icon: '←', color: 'var(--color-text-muted)' },
  token_sample: { icon: '◎', color: 'var(--color-accent-amber)' },
  final: { icon: '★', color: 'var(--color-accent-green)' },
  error: { icon: '✗', color: 'var(--color-accent-red)' },
};

function formatEvent(event: AlgoPilotEvent): string {
  const e = event as Record<string, unknown>;
  switch (event.type) {
    case 'phase_start': return `Phase: ${e.phase}`;
    case 'phase_done': return `Done: ${e.phase}`;
    case 'node_enter': return `Enter: ${e.node_id}`;
    case 'node_exit': return `Exit: ${e.node_id}`;
    case 'token_sample': return `+${e.input_tokens || 0}/${e.output_tokens || 0} tok`;
    case 'final': return `Final: ${e.accepted ? 'AC' : 'WA'} (${((e.pass_rate as number) * 100).toFixed(0)}%)`;
    case 'error': return `Error: ${(e.message as string || '').slice(0, 40)}`;
    default: return event.type;
  }
}

export default function EventFeed({ events }: EventFeedProps) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events.length]);

  const visible = events.slice(-50);

  return (
    <div className="event-feed">
      <div className="event-feed__header">Events</div>
      <div className="event-feed__list">
        {visible.map((ev, i) => {
          const cfg = typeConfig[ev.type] || { icon: '·', color: 'var(--color-text-muted)' };
          return (
            <div key={i} className="event-feed__item" style={{ borderLeftColor: cfg.color }}>
              <span className="event-feed__icon" style={{ color: cfg.color }}>{cfg.icon}</span>
              <span className="event-feed__text">{formatEvent(ev)}</span>
            </div>
          );
        })}
        <div ref={endRef} />
      </div>

      <style>{`
        .event-feed {
          padding: var(--space-md);
          height: 100%;
          display: flex;
          flex-direction: column;
        }
        .event-feed__header {
          font-size: var(--font-size-xs);
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.06em;
          color: var(--color-text-muted);
          margin-bottom: var(--space-sm);
        }
        .event-feed__list {
          flex: 1;
          overflow-y: auto;
          display: flex;
          flex-direction: column;
          gap: 2px;
        }
        .event-feed__item {
          display: flex;
          align-items: center;
          gap: var(--space-sm);
          padding: 4px 8px;
          border-left: 2px solid;
          border-radius: 0 4px 4px 0;
          background: var(--color-bg-glass);
          animation: slide-in-right 0.2s ease-out;
          font-size: var(--font-size-xs);
        }
        .event-feed__icon {
          font-size: 11px;
          flex-shrink: 0;
          width: 14px;
          text-align: center;
        }
        .event-feed__text {
          color: var(--color-text-secondary);
          font-family: var(--font-mono);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
      `}</style>
    </div>
  );
}
