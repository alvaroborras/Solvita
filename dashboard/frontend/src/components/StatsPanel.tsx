import { useEffect, useRef, useState } from 'react';

import { useElapsedClock } from '../hooks/useElapsedClock';
import type { FinalArtifactSnapshot } from '../types/artifacts';
import type { AlgoPilotEvent } from '../types/events';
import type { LiveProgress } from '../utils/buildLiveProgress';

interface StatsPanelProps {
  artifact: FinalArtifactSnapshot | null;
  events: AlgoPilotEvent[];
  liveProgress: LiveProgress;
  mode: 'live' | 'replay' | 'idle';
  wsStatus: string;
}

function AnimatedValue({ value, color }: { value: string; color: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const prevRef = useRef(value);

  useEffect(() => {
    if (prevRef.current !== value && ref.current) {
      ref.current.style.animation = 'none';
      void ref.current.offsetHeight;
      ref.current.style.animation = 'count-update 0.3s ease-out';
      prevRef.current = value;
    }
  }, [value]);

  return <span ref={ref} style={{ color, fontWeight: 600, fontFamily: 'var(--font-mono)' }}>{value}</span>;
}

function eventNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function eventCountMetrics(events: AlgoPilotEvent[]): {
  elapsedSeconds: number;
  llmCalls: number;
  totalTokens: number | null;
} {
  let startTs: number | null = null;
  let lastTs: number | null = null;
  let llmCalls = 0;
  let latestExplicitTotal: number | null = null;
  let summedImplicitTokens = 0;

  for (const event of events) {
    if (startTs === null && event.type === 'solve_start') {
      startTs = event.ts;
    }
    lastTs = event.ts;

    if (event.type !== 'token_sample') {
      continue;
    }

    llmCalls += 1;
    const record = event as Record<string, unknown>;
    const total = eventNumber(record.total);
    if (total !== null) {
      latestExplicitTotal = total;
      continue;
    }

    const prompt = eventNumber(record.prompt_tokens) ?? eventNumber(record.input_tokens) ?? 0;
    const completion = eventNumber(record.completion_tokens) ?? eventNumber(record.output_tokens) ?? 0;
    summedImplicitTokens += prompt + completion;
  }

  return {
    elapsedSeconds: startTs === null || lastTs === null ? 0 : Math.max(0, Math.round(lastTs - startTs)),
    llmCalls,
    totalTokens: latestExplicitTotal ?? (summedImplicitTokens > 0 ? summedImplicitTokens : null),
  };
}

function finalMetrics(events: AlgoPilotEvent[]): {
  iterations: number | null;
  llmCalls: number | null;
  totalTokens: number | null;
} {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];
    if (event.type !== 'final') {
      continue;
    }

    const record = event as Record<string, unknown>;
    const prompt = eventNumber(record.prompt_tokens) ?? 0;
    const completion = eventNumber(record.completion_tokens) ?? 0;

    return {
      iterations: eventNumber(record.iterations),
      llmCalls: eventNumber(record.llm_calls),
      totalTokens: eventNumber(record.total_tokens) ?? (prompt + completion > 0 ? prompt + completion : null),
    };
  }

  return {
    iterations: null,
    llmCalls: null,
    totalTokens: null,
  };
}

function artifactTokens(artifact: FinalArtifactSnapshot | null): number | null {
  if (!artifact) {
    return null;
  }

  const prompt = artifact.promptTokens ?? 0;
  const completion = artifact.completionTokens ?? 0;
  if (prompt === 0 && completion === 0) {
    return null;
  }
  return prompt + completion;
}

function formatTime(seconds: number): string {
  if (seconds <= 0) return '0s';
  if (seconds < 60) return `${seconds.toFixed(0)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

function formatTokens(value: number | null): string {
  if (value === null) return '—';
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return String(value);
}

function statusColor(mode: StatsPanelProps['mode'], wsStatus: string): string {
  if (mode === 'replay') {
    return 'var(--color-accent-purple)';
  }
  if (wsStatus === 'connected') {
    return 'var(--color-accent-green)';
  }
  if (wsStatus === 'connecting' || wsStatus === 'reconnecting') {
    return 'var(--color-accent-amber)';
  }
  if (wsStatus === 'error') {
    return 'var(--color-accent-red)';
  }
  return 'var(--color-text-muted)';
}

export default function StatsPanel({
  artifact,
  events,
  liveProgress,
  mode,
  wsStatus,
}: StatsPanelProps) {
  const counts = eventCountMetrics(events);
  const final = finalMetrics(events);
  const iterations = liveProgress.metrics.iteration ?? final.iterations ?? 0;
  const llmCalls = final.llmCalls ?? artifact?.llmCalls ?? counts.llmCalls;
  const totalTokens = final.totalTokens ?? artifactTokens(artifact) ?? counts.totalTokens;
  const running = mode === 'live' && events.length > 0;
  const [clockStartAtMs, setClockStartAtMs] = useState<number | null>(() => (
    running ? Date.now() - (counts.elapsedSeconds * 1000) : null
  ));

  useEffect(() => {
    setClockStartAtMs(running ? Date.now() - (counts.elapsedSeconds * 1000) : null);
  }, [counts.elapsedSeconds, running]);

  const liveElapsedSeconds = useElapsedClock({ startAtMs: clockStartAtMs, running });
  const elapsedSeconds = running
    ? Math.max(counts.elapsedSeconds, liveElapsedSeconds)
    : counts.elapsedSeconds;

  const cards = [
    { label: 'Time', value: formatTime(elapsedSeconds), color: 'var(--color-accent-blue)' },
    { label: 'Iters', value: String(iterations), color: 'var(--color-accent-green)' },
    { label: 'LLM', value: String(llmCalls), color: 'var(--color-accent-amber)' },
    { label: 'Tokens', value: formatTokens(totalTokens), color: 'var(--color-accent-purple)' },
  ];

  const indicatorColor = statusColor(mode, wsStatus);
  const statusLabel = mode === 'replay' ? 'replay ready' : wsStatus;

  return (
    <div className="stats-panel">
      <div className="stats-panel__live">
        <div
          className="stats-panel__indicator"
          style={{
            background: indicatorColor,
            boxShadow: mode === 'live' && wsStatus === 'connected'
              ? `0 0 12px ${indicatorColor}`
              : 'none',
          }}
        />
        <span className="stats-panel__status">{statusLabel}</span>
      </div>
      {cards.map((card) => (
        <div key={card.label} className="stats-panel__card">
          <span className="stats-panel__label">{card.label}</span>
          <AnimatedValue value={card.value} color={card.color} />
        </div>
      ))}

      <style>{`
        .stats-panel {
          display: flex;
          align-items: center;
          flex-wrap: wrap;
          justify-content: flex-end;
          gap: var(--space-sm);
        }
        .stats-panel__live {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          padding: 8px 12px;
          border-radius: 999px;
          border: 1px solid var(--color-border-subtle);
          background: var(--color-control-bg);
          backdrop-filter: blur(12px);
        }
        .stats-panel__indicator {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          transition: all var(--transition-normal);
        }
        .stats-panel__status {
          font-size: 11px;
          font-weight: 700;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          color: var(--color-text-secondary);
        }
        .stats-panel__card {
          display: flex;
          flex-direction: column;
          align-items: flex-start;
          gap: 4px;
          min-width: 84px;
          padding: 10px 12px;
          background: var(--color-stat-card-bg);
          border: 1px solid var(--color-border-subtle);
          border-radius: 14px;
          font-size: var(--font-size-sm);
          backdrop-filter: blur(10px);
        }
        .stats-panel__label {
          color: var(--color-text-muted);
          font-size: 10px;
          text-transform: uppercase;
          letter-spacing: 0.08em;
        }
      `}</style>
    </div>
  );
}
