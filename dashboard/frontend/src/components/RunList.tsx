import { useDeferredValue, useEffect, useMemo, useRef, useState } from 'react';

import { useI18n } from '../i18n';
import { deleteRun } from '../utils/runApi';

interface RunSummary {
  run_id: string;
  problem_name?: string;
  problem_id?: string;
  problem_family?: string;
  started_at: string;
  completed_at?: string;
  status: string;
  final_status?: string | null;
  iterations?: number | null;
  pass_rate?: number | null;
  event_count?: number;
}

interface RunListProps {
  onSelectReplay: (runId: string) => void;
  onSelectLive: (runId: string) => void;
  activeRunId?: string | null;
  mode?: 'live' | 'replay' | 'idle';
  onDeletedRun?: (runId: string) => void;
}

type RunFilter = 'all' | 'live' | 'completed';
type RunSelectionMode = 'live' | 'replay';

function formatPassRate(value: number | null | undefined): string {
  if (typeof value !== 'number') return '—';
  return `${Math.round(value * 100)}%`;
}

function polledSelectionMode(run: RunSummary): RunSelectionMode {
  return run.status === 'running' ? 'live' : 'replay';
}

export default function RunList({
  onSelectReplay,
  onSelectLive,
  activeRunId = null,
  mode = 'idle',
  onDeletedRun,
}: RunListProps) {
  const { t } = useI18n();
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<RunFilter>('all');
  const [deleteTarget, setDeleteTarget] = useState<RunSummary | null>(null);
  const [deletePending, setDeletePending] = useState(false);
  const deletedRunIdsRef = useRef<Set<string>>(new Set());
  const deferredQuery = useDeferredValue(query);

  useEffect(() => {
    const fetchRuns = () => {
      fetch('/api/runs')
        .then((r) => r.json())
        .then((data) => {
          const nextRuns = (data.runs || []).filter(
            (run: RunSummary) => !deletedRunIdsRef.current.has(run.run_id),
          );
          setRuns(nextRuns);
        })
        .catch(() => {});
    };
    fetchRuns();
    const interval = setInterval(fetchRuns, 5000);
    return () => clearInterval(interval);
  }, []);

  const visibleRuns = useMemo(() => {
    const normalizedQuery = deferredQuery.trim().toLowerCase();
    return runs.filter((run) => {
      if (filter === 'live' && run.status !== 'running') return false;
      if (filter === 'completed' && run.status !== 'completed') return false;
      if (!normalizedQuery) return true;
      const haystack = `${run.problem_name || ''} ${run.problem_id || ''} ${run.run_id}`.toLowerCase();
      return haystack.includes(normalizedQuery);
    });
  }, [deferredQuery, filter, runs]);

  const selectRun = (run: RunSummary) => {
    const nextMode: RunSelectionMode = activeRunId === run.run_id && mode !== 'idle'
      ? mode
      : polledSelectionMode(run);
    if (activeRunId === run.run_id && mode === nextMode) {
      return;
    }

    if (nextMode === 'live') {
      onSelectLive(run.run_id);
      return;
    }

    onSelectReplay(run.run_id);
  };

  const confirmDelete = async () => {
    if (!deleteTarget || deletePending) return;
    setDeletePending(true);
    try {
      await deleteRun(deleteTarget.run_id);
      deletedRunIdsRef.current.add(deleteTarget.run_id);
      setRuns((current) => current.filter((run) => run.run_id !== deleteTarget.run_id));
      onDeletedRun?.(deleteTarget.run_id);
      setDeleteTarget(null);
    } finally {
      setDeletePending(false);
    }
  };

  return (
    <div className="run-list">
      <div className="run-list__headerRow">
        <div className="run-list__header">{t('runListTitle')}</div>
        <div className="run-list__count">{visibleRuns.length}</div>
      </div>

      <div className="run-list__toolbar">
        <input
          className="run-list__search"
          type="text"
          placeholder={t('searchRuns')}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <div className="run-list__filters">
          {(['all', 'live', 'completed'] as const).map((nextFilter) => (
            <button
              key={nextFilter}
              type="button"
              className={`run-list__filter ${filter === nextFilter ? 'run-list__filter--active' : ''}`}
              onClick={() => setFilter(nextFilter)}
            >
              {nextFilter === 'all' ? t('all') : nextFilter === 'live' ? t('live') : t('completed')}
            </button>
          ))}
        </div>
      </div>

      {visibleRuns.length === 0 && <div className="run-list__empty">{t('noRunsMatch')}</div>}
      {visibleRuns.map((run) => {
        const selected = activeRunId === run.run_id && mode !== 'idle';
        const selectionMode: RunSelectionMode = activeRunId === run.run_id && mode !== 'idle'
          ? mode
          : polledSelectionMode(run);
        return (
          <article
            key={run.run_id}
            className={[
              'run-list__item',
              selected ? 'run-list__item--selected' : '',
              mode === 'live' && selected ? 'run-list__item--live' : '',
              mode === 'replay' && selected ? 'run-list__item--replay' : '',
            ].join(' ')}
          >
            <button
              type="button"
              className="run-list__select"
              aria-pressed={selected}
              onClick={() => selectRun(run)}
            >
              <div className="run-list__info">
                <div className="run-list__nameRow">
                  <span className="run-list__name">{run.problem_name || run.problem_id || run.run_id.slice(0, 8)}</span>
                  <span className={`run-list__status run-list__status--${run.status}`}>
                    {run.status === 'running' ? t('live') : (run.final_status || t('replay'))}
                  </span>
                  {run.problem_family && (
                    <span className="run-list__family">{run.problem_family}</span>
                  )}
                </div>
                <span className="run-list__meta">{run.started_at?.slice(11, 19) || ''}</span>
                <div className="run-list__stats">
                  <span>{t('pass')} {formatPassRate(run.pass_rate)}</span>
                  <span>{t('iters')} {run.iterations ?? '—'}</span>
                </div>
              </div>
            </button>
            <div className="run-list__actions">
              {selectionMode === 'live' && (
                <button
                  type="button"
                  className="run-list__btn run-list__btn--live"
                  disabled={selected}
                  onClick={() => selectRun(run)}
                >
                  {selected ? t('watching') : t('watch')}
                </button>
              )}
              {selectionMode === 'replay' && (
                <button
                  type="button"
                  className="run-list__btn run-list__btn--replay"
                  disabled={selected}
                  onClick={() => selectRun(run)}
                >
                  {selected ? t('opened') : t('replay')}
                </button>
              )}
              {run.status !== 'running' && (
                <button
                  type="button"
                  className="run-list__btn run-list__btn--danger"
                  onClick={() => setDeleteTarget(run)}
                >
                  {t('delete')}
                </button>
              )}
            </div>
          </article>
        );
      })}

      {deleteTarget && (
        <div className="run-list__modalBackdrop" role="presentation">
          <div className="run-list__modal surface-card" role="dialog" aria-modal="true" aria-labelledby="run-delete-title">
            <h3 id="run-delete-title">{t('deleteRunTitle')}</h3>
            <p>
              This permanently deletes the dashboard record for <strong>{deleteTarget.problem_name || deleteTarget.run_id}</strong>
              {' '}{t('deleteRunBodySuffix')}
            </p>
            <div className="run-list__modalActions">
              <button type="button" className="run-list__btn" disabled={deletePending} onClick={() => setDeleteTarget(null)}>
                {t('cancel')}
              </button>
              <button type="button" className="run-list__btn run-list__btn--danger" disabled={deletePending} onClick={() => { void confirmDelete(); }}>
                {deletePending ? t('deleting') : t('deletePermanently')}
              </button>
            </div>
          </div>
        </div>
      )}

      <style>{`
        .run-list {
          padding: 0;
        }
        .run-list__headerRow {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 10px;
          margin-bottom: var(--space-md);
        }
        .run-list__header {
          font-size: 12px;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.1em;
          color: var(--color-text-muted);
        }
        .run-list__count {
          min-width: 28px;
          height: 28px;
          border-radius: 999px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          background: rgba(255,255,255,0.06);
          color: var(--color-text-secondary);
          font-size: 12px;
          font-weight: 700;
        }
        .run-list__toolbar {
          display: grid;
          gap: 10px;
          margin-bottom: 12px;
        }
        .run-list__search {
          width: 100%;
          height: 40px;
          padding: 0 12px;
          border-radius: 12px;
          border: 1px solid var(--color-border-subtle);
          background: rgba(255,255,255,0.05);
          color: var(--color-text-primary);
          font-size: 14px;
          outline: none;
        }
        .run-list__search:focus {
          border-color: rgba(64, 139, 255, 0.28);
        }
        .run-list__filters {
          display: flex;
          gap: 8px;
        }
        .run-list__filter {
          height: 32px;
          padding: 0 12px;
          border-radius: 999px;
          border: 1px solid var(--color-border-subtle);
          background: rgba(255,255,255,0.04);
          color: var(--color-text-muted);
          font-size: 11px;
          font-weight: 700;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          cursor: pointer;
        }
        .run-list__filter--active {
          background: rgba(64, 139, 255, 0.16);
          color: var(--color-accent-blue);
          border-color: rgba(64, 139, 255, 0.24);
        }
        .run-list__empty {
          font-size: var(--font-size-sm);
          color: var(--color-text-muted);
          font-style: italic;
          padding: 10px 0;
        }
        .run-list__item {
          display: grid;
          grid-template-columns: minmax(0, 1fr);
          align-items: stretch;
          gap: 12px;
          padding: 12px;
          margin-bottom: 8px;
          background: linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0.02));
          border: 1px solid var(--color-border-subtle);
          border-radius: 14px;
          transition: border-color var(--transition-fast), transform var(--transition-fast), box-shadow var(--transition-fast);
        }
        .run-list__item:hover {
          transform: translateY(-1px);
          border-color: rgba(255,255,255,0.16);
        }
        .run-list__select {
          width: 100%;
          min-width: 0;
          border: none;
          background: transparent;
          color: inherit;
          text-align: left;
          cursor: pointer;
        }
        .run-list__select:focus-visible {
          outline: 2px solid rgba(64, 139, 255, 0.46);
          outline-offset: 2px;
          border-radius: 10px;
        }
        .run-list__item--selected {
          border-color: rgba(64, 139, 255, 0.28);
          box-shadow: 0 12px 26px rgba(64, 139, 255, 0.14);
        }
        .run-list__info {
          display: flex;
          flex-direction: column;
          gap: 4px;
          min-width: 0;
          flex: 1;
        }
        .run-list__nameRow {
          display: flex;
          align-items: center;
          gap: 8px;
          min-width: 0;
        }
        .run-list__name {
          font-size: 15px;
          font-weight: 600;
          color: var(--color-text-primary);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .run-list__status {
          padding: 3px 8px;
          border-radius: 999px;
          font-size: 10px;
          font-weight: 700;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          background: rgba(255,255,255,0.06);
          color: var(--color-text-secondary);
        }
        .run-list__status--running {
          background: rgba(83, 208, 168, 0.14);
          color: var(--color-accent-green);
        }
        .run-list__status--completed {
          background: rgba(64, 139, 255, 0.14);
          color: var(--color-accent-blue);
        }
        .run-list__family {
          padding: 3px 8px;
          border-radius: 999px;
          font-size: 10px;
          font-weight: 700;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          background: rgba(255,255,255,0.05);
          color: var(--color-text-secondary);
        }
        .run-list__meta {
          font-size: 12px;
          color: var(--color-text-muted);
          font-family: var(--font-mono);
        }
        .run-list__stats {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          font-size: 11px;
          color: var(--color-text-secondary);
          letter-spacing: 0.06em;
          text-transform: uppercase;
        }
        .run-list__actions {
          width: 100%;
          display: flex;
          flex-wrap: wrap;
          justify-content: flex-start;
          gap: 8px;
          padding-top: 2px;
        }
        .run-list__btn {
          font-size: 12px;
          font-weight: 700;
          padding: 8px 12px;
          border: none;
          border-radius: 999px;
          cursor: pointer;
          transition: all var(--transition-fast);
          white-space: nowrap;
        }
        .run-list__btn:hover {
          transform: translateY(-1px);
        }
        .run-list__btn:disabled {
          opacity: 0.55;
          cursor: not-allowed;
          transform: none;
        }
        .run-list__btn--live {
          background: rgba(80, 227, 194, 0.15);
          color: var(--color-accent-green);
        }
        .run-list__btn--replay {
          background: rgba(0, 112, 243, 0.15);
          color: var(--color-accent-blue);
        }
        .run-list__btn--danger {
          background: rgba(247, 93, 93, 0.14);
          color: var(--color-accent-red);
        }
        .run-list__modalBackdrop {
          position: fixed;
          inset: 0;
          background: rgba(7, 16, 25, 0.68);
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 24px;
          z-index: 30;
        }
        .run-list__modal {
          width: min(100%, 440px);
          display: grid;
          gap: 14px;
          padding: 20px;
        }
        .run-list__modalActions {
          display: flex;
          justify-content: flex-end;
          gap: 10px;
        }
      `}</style>
    </div>
  );
}
