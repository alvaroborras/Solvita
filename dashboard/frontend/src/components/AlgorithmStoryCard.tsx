import { useEffect, useMemo, useState } from 'react';
import { AlgorithmVisualization } from '../types/artifacts';
import BasicDpStoryView from './algorithm-story/BasicDpStoryView';
import BinarySearchStoryView from './algorithm-story/BinarySearchStoryView';
import BfsStoryView from './algorithm-story/BfsStoryView';
import DfsRecursionStoryView from './algorithm-story/DfsRecursionStoryView';
import GreedyIntervalStoryView from './algorithm-story/GreedyIntervalStoryView';
import MonotonicStackStoryView from './algorithm-story/MonotonicStackStoryView';
import PrefixSumStoryView from './algorithm-story/PrefixSumStoryView';
import SlidingWindowStoryView from './algorithm-story/SlidingWindowStoryView';
import TopologicalSortStoryView from './algorithm-story/TopologicalSortStoryView';
import TwoPointersStoryView from './algorithm-story/TwoPointersStoryView';
import UnionFindStoryView from './algorithm-story/UnionFindStoryView';
import { buildPlaybackSteps } from '../utils/algorithmStoryPlayback';
import { algorithmFamilyLabel, localizeAlgorithmStory, localizeDashboardText, useI18n } from '../i18n';

interface AlgorithmStoryCardProps {
  story: AlgorithmVisualization | null;
  mode?: 'live' | 'replay' | 'idle';
  revision?: number;
}

export default function AlgorithmStoryCard({ story: rawStory, mode = 'idle', revision = 0 }: AlgorithmStoryCardProps) {
  const { language, t } = useI18n();
  const displayStory = useMemo(
    () => (rawStory ? localizeAlgorithmStory(language, rawStory) : null),
    [language, rawStory],
  );
  const [cursor, setCursor] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const playbackSteps = useMemo(() => buildPlaybackSteps(displayStory), [displayStory]);
  const stepCount = playbackSteps.length || displayStory?.steps.length || 0;

  useEffect(() => {
    setCursor(0);
    setPlaying(false);
    setSpeed(1);
  }, [displayStory?.title, displayStory?.family, displayStory?.steps.length, revision]);

  useEffect(() => {
    if (mode !== 'live' || !displayStory?.supported || !displayStory.liveAutoplay || stepCount === 0) return;
    const nextCursor = Math.max(0, Math.min(stepCount - 1, displayStory.liveCursor ?? 0));
    setCursor(nextCursor);
    setPlaying(true);
  }, [displayStory?.liveAutoplay, displayStory?.liveCursor, displayStory?.supported, mode, revision, stepCount]);

  useEffect(() => {
    if (!displayStory?.supported || !playing || cursor >= stepCount - 1) return;
    const timer = window.setTimeout(() => setCursor((prev) => prev + 1), 1200 / speed);
    return () => window.clearTimeout(timer);
  }, [playing, cursor, speed, stepCount, displayStory]);

  useEffect(() => {
    if (!displayStory?.supported) return;
    if (cursor >= stepCount - 1) {
      setPlaying(false);
    }
  }, [cursor, stepCount, displayStory]);

  if (!displayStory) return null;

  const story: AlgorithmVisualization = displayStory;

  if (!story.supported) {
    return (
      <section className="algorithm-story surface-card">
        <div className="surface-kicker">{t('algorithmStory')}</div>
        <h2 className="surface-title">{t('teachingPlaybackUnavailable')}</h2>
        <p className="algorithm-story__fallback">{story.fallbackText}</p>
      </section>
    );
  }

  if (stepCount === 0) {
    return (
      <section className="algorithm-story surface-card">
        <div className="surface-kicker">{t('algorithmStory')}</div>
        <h2 className="surface-title">{story.title}</h2>
        <p className="algorithm-story__fallback">{t('playbackDataMissing')}</p>
      </section>
    );
  }

  const activePlayback = playbackSteps[cursor];
  const step = activePlayback?.viewStep ?? story.steps[cursor];
  const stepChanges = activePlayback?.changes ?? [];
  const progressPercent = stepCount > 0 ? ((cursor + 1) / stepCount) * 100 : 0;
  const revealedCount = mode === 'live' && story.liveAutoplay ? Math.max(cursor + 1, 1) : stepCount;
  const visiblePlaybackSteps = mode === 'live' && story.liveAutoplay
    ? playbackSteps.slice(0, revealedCount)
    : playbackSteps;

  return (
    <section className="algorithm-story surface-card">
      <div className="algorithm-story__header">
        <div>
          <div className="surface-kicker">{t('algorithmStory')}</div>
          <h2 className="surface-title">{story.title}</h2>
        </div>
        <div className="algorithm-story__badges">
          <span className="algorithm-story__badge">{algorithmFamilyLabel(language, story.family)}</span>
          <span className="algorithm-story__badge">{story.mode}</span>
          <span className="algorithm-story__badge">{story.sampleSource || t('publicSample')}</span>
        </div>
      </div>

      <p className="algorithm-story__summary">{story.summary}</p>
      <div className="algorithm-story__meta">
        <span>{story.sampleSource || t('publicSample')}</span>
        {story.sampleFocus && <span>{story.sampleFocus}</span>}
        {story.traceSource && <span>{story.traceSource}</span>}
        {story.sampleValidated && story.sampleMatches === true && <span>{t('codeValidated')}</span>}
        {story.sampleValidated && story.sampleMatches === false && <span>{t('codeMismatch')}</span>}
        <span>{stepCount} {t('steps')}</span>
      </div>

      {story.validationNote && (
        <p className="algorithm-story__summary">{story.validationNote}</p>
      )}

      <details className="algorithm-story__sample">
        <summary className="algorithm-story__sampleToggle">{t('viewSampleIo')}</summary>
        <div className="algorithm-story__sampleGrid">
          <div className="algorithm-story__sampleBlock">
            <div className="algorithm-story__sampleLabel">{t('sampleSource')}</div>
            <div className="algorithm-story__sampleText">{story.sampleSource || t('publicSample')}</div>
          </div>
          {story.sampleFocus && (
            <div className="algorithm-story__sampleBlock">
              <div className="algorithm-story__sampleLabel">{t('sampleFocus')}</div>
              <div className="algorithm-story__sampleText">{story.sampleFocus}</div>
            </div>
          )}
          {story.sampleInput && (
            <div className="algorithm-story__sampleBlock algorithm-story__sampleBlock--wide">
              <div className="algorithm-story__sampleLabel">{t('sampleInput')}</div>
              <pre className="algorithm-story__sampleCode">{story.sampleInput}</pre>
            </div>
          )}
          {story.sampleOutput && (
            <div className="algorithm-story__sampleBlock algorithm-story__sampleBlock--wide">
              <div className="algorithm-story__sampleLabel">{t('expectedOutput')}</div>
              <pre className="algorithm-story__sampleCode">{story.sampleOutput}</pre>
            </div>
          )}
        </div>
      </details>

      <div className="algorithm-story__body">
        <div className="algorithm-story__visual">
          {story.family === 'bfs' && <BfsStoryView step={step} />}
          {story.family === 'dfs_recursion' && <DfsRecursionStoryView step={step} />}
          {story.family === 'basic_dp' && <BasicDpStoryView step={step} />}
          {story.family === 'two_pointers' && <TwoPointersStoryView step={step} />}
          {story.family === 'sliding_window' && <SlidingWindowStoryView step={step} />}
          {story.family === 'binary_search' && <BinarySearchStoryView step={step} />}
          {story.family === 'prefix_sum' && <PrefixSumStoryView step={step} />}
          {story.family === 'union_find' && <UnionFindStoryView step={step} />}
          {story.family === 'topological_sort' && <TopologicalSortStoryView step={step} />}
          {story.family === 'greedy_interval' && <GreedyIntervalStoryView step={step} />}
          {story.family === 'monotonic_stack' && <MonotonicStackStoryView step={step} />}
        </div>

        <div className="algorithm-story__timeline">
          <div className="algorithm-story__stepCard">
            <div className="algorithm-story__stepLabel">{t('step')} {step?.step ?? 0}</div>
            <div className="algorithm-story__stepTitle">{step?.label || t('noStepSelected')}</div>
            <p className="algorithm-story__stepCaption">{step?.caption || ''}</p>
            <div className="algorithm-story__changes">
              <div className="algorithm-story__changesLabel">{t('stateChanges')}</div>
              {stepChanges.length > 0 ? (
                <div className="algorithm-story__changesList">
                  {stepChanges.map((change, index) => (
                    <div key={`${step?.step ?? 0}-change-${index}`} className="algorithm-story__changeItem">
                      {localizeDashboardText(language, change)}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="algorithm-story__changeItem algorithm-story__changeItem--muted">
                  {t('continuousStep')}
                </div>
              )}
            </div>
          </div>

          <div className="algorithm-story__progress">
            <div className="algorithm-story__progressBar">
              <div className="algorithm-story__progressFill" style={{ width: `${progressPercent}%` }} />
            </div>
            <div className="algorithm-story__progressMeta">
              <span>{cursor + 1}/{stepCount}</span>
              <span>{Math.round(progressPercent)}%</span>
            </div>
          </div>

          <div className="algorithm-story__controls">
            <button
              type="button"
              className="algorithm-story__controlBtn"
              onClick={() => {
                setCursor((prev) => Math.max(0, prev - 1));
                setPlaying(false);
              }}
            >
              {t('prev')}
            </button>
            <button type="button" className="algorithm-story__controlBtn algorithm-story__controlBtn--primary" onClick={() => setPlaying((prev) => !prev)}>
              {playing ? t('pause') : t('play')}
            </button>
            <button
              type="button"
              className="algorithm-story__controlBtn"
              onClick={() => {
                setCursor((prev) => Math.min(stepCount - 1, prev + 1));
                setPlaying(false);
              }}
            >
              {t('next')}
            </button>
            <div className="algorithm-story__speedGroup">
              {[0.75, 1, 1.5].map((value) => (
                <button
                  key={value}
                  type="button"
                  className={`algorithm-story__speedBtn ${speed === value ? 'algorithm-story__speedBtn--active' : ''}`}
                  onClick={() => setSpeed(value)}
                >
                  {value}x
                </button>
              ))}
            </div>
          </div>

          <div className="algorithm-story__stepsList">
            {visiblePlaybackSteps.map(({ viewStep }, index) => (
              <button
                key={`${viewStep.step}-${index}`}
                type="button"
                className={`algorithm-story__stepItem ${index === cursor ? 'algorithm-story__stepItem--active' : ''}`}
                onClick={() => {
                  setCursor(index);
                  setPlaying(false);
                }}
              >
                <span className="algorithm-story__stepItemIndex">{viewStep.step}</span>
                <span className="algorithm-story__stepItemText">{viewStep.label}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
