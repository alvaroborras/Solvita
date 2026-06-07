import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import AlgorithmStoryCard from './components/AlgorithmStoryCard';
import EvidenceWorkbench from './components/EvidenceWorkbench';
import FailureAnalysisCard from './components/FailureAnalysisCard';
import FinalSummaryCard from './components/FinalSummaryCard';
import Layout from './components/Layout';
import LiveProgressPanel from './components/LiveProgressPanel';
import LiveStatusStrip from './components/LiveStatusStrip';
import PlaybackControls from './components/PlaybackControls';
import ProblemPanel from './components/ProblemPanel';
import ReplayScrubber from './components/ReplayScrubber';
import RunContextCard from './components/RunContextCard';
import RunList from './components/RunList';
import SessionBar from './components/SessionBar';
import SolveJourneyMap from './components/SolveJourneyMap';
import SolveTimeline from './components/SolveTimeline';
import StageDetailPanel from './components/StageDetailPanel';
import StatsPanel from './components/StatsPanel';
import { useRunSession } from './hooks/useRunSession';
import type { AlgoPilotEvent } from './types/events';
import type { JourneyStageId, JourneyTimelineEntry } from './types/journey';
import { buildSolveJourney } from './utils/buildSolveJourney';
import { buildLiveProgress } from './utils/buildLiveProgress';
import { buildFailureAnalysis } from './utils/failureAnalysis';
import { extractRunArtifacts } from './utils/extractRunArtifacts';
import { cancelRun, createRun } from './utils/runApi';

function latestProcessedSeq(events: AlgoPilotEvent[]): number {
  if (events.length === 0) return -1;
  const last = events[events.length - 1];
  return typeof last.seq === 'number' ? last.seq : events.length - 1;
}

function latestTimelineForStage(
  entries: JourneyTimelineEntry[],
  stageId: JourneyStageId | null,
): JourneyTimelineEntry | null {
  if (!stageId) return entries.length > 0 ? entries[entries.length - 1] : null;
  const filtered = entries.filter((entry) => entry.stageId === stageId);
  return filtered.length > 0 ? filtered[filtered.length - 1] : null;
}

function deriveProblemName(
  detail: { problemId?: string; problem?: Record<string, unknown> } | null,
  events: AlgoPilotEvent[],
): string {
  const metadata = ((detail?.problem?._metadata as Record<string, unknown> | undefined) || {});
  const fromMetadata = metadata.name || metadata.question_id || metadata.problem_id;
  if (fromMetadata) return String(fromMetadata);
  const solveStart = events.find((event) => event.type === 'solve_start') as
    | { problem_name?: string; problem_id?: string }
    | undefined;
  return solveStart?.problem_name || solveStart?.problem_id || detail?.problemId || '';
}

function clampReplayCursor(cursor: number, total: number): number {
  return Math.max(0, Math.min(cursor, total));
}

export default function App() {
  const {
    dropRun,
    reconnect,
    restoreLatestRun,
    selectLiveRun,
    selectReplayRun,
    session,
    setReplayCursor,
    setSelectedStageId,
    setSelectedTimelineId,
  } = useRunSession();

  const [showProblemPanel, setShowProblemPanel] = useState(false);
  const [replayPlaying, setReplayPlaying] = useState(false);
  const [replaySpeed, setReplaySpeed] = useState(1);
  const [interruptPendingRunId, setInterruptPendingRunId] = useState<string | null>(null);
  const previousModeRef = useRef(session.mode);
  const previousRunIdRef = useRef(session.runId);
  const sessionStateRef = useRef(session);
  sessionStateRef.current = session;

  const displayEvents = useMemo(
    () => (session.mode === 'replay' ? session.events.slice(0, session.replayCursor) : session.events),
    [session.events, session.mode, session.replayCursor],
  );

  const canonicalJourney = useMemo(() => buildSolveJourney(session.events), [session.events]);
  const displayJourney = useMemo(() => buildSolveJourney(displayEvents), [displayEvents]);
  const canonicalArtifacts = useMemo(() => extractRunArtifacts(session.events), [session.events]);
  const displayArtifacts = useMemo(() => extractRunArtifacts(displayEvents), [displayEvents]);

  const liveProgress = useMemo(
    () => buildLiveProgress({ events: displayEvents, artifact: displayArtifacts.finalArtifact }),
    [displayArtifacts.finalArtifact, displayEvents],
  );

  const failureAnalysis = useMemo(
    () => buildFailureAnalysis({
      finalStatus: canonicalJourney.finalStatus,
      artifact: canonicalArtifacts.finalArtifact,
      timeline: canonicalJourney.timeline,
      events: session.events,
    }),
    [canonicalArtifacts.finalArtifact, canonicalJourney.finalStatus, canonicalJourney.timeline, session.events],
  );

  const currentStageId = displayJourney.activeStageId || displayJourney.lastVisitedStageId;
  const currentStage = displayJourney.stages.find((stage) => stage.id === currentStageId) || null;
  const progressSeq = latestProcessedSeq(displayEvents);
  const totalStages = displayJourney.stages.length;
  const completedStageCount = displayJourney.stages.filter((stage) => stage.status === 'completed').length;
  const touchedStageCount = displayJourney.stages.filter((stage) => stage.status !== 'waiting').length;

  const problemName = useMemo(
    () => deriveProblemName(session.runDetail, session.events),
    [session.events, session.runDetail],
  );

  useEffect(() => {
    if (previousRunIdRef.current !== session.runId) {
      setReplayPlaying(false);
      setReplaySpeed(1);
    }

    if (
      previousModeRef.current === 'live'
      && session.mode === 'replay'
      && session.replayCursor === 0
      && session.events.length > 0
    ) {
      setReplayCursor(session.events.length);
    }

    if (session.mode !== 'replay') {
      setReplayPlaying(false);
    }

    previousModeRef.current = session.mode;
    previousRunIdRef.current = session.runId;
  }, [session.events.length, session.mode, session.replayCursor, session.runId, setReplayCursor]);

  useEffect(() => {
    if (session.mode !== 'replay' || !replayPlaying) {
      return;
    }

    if (session.replayCursor >= session.events.length) {
      setReplayPlaying(false);
      return;
    }

    const current = session.events[Math.max(0, session.replayCursor - 1)];
    const next = session.events[session.replayCursor];
    let delay = 200;
    if (current && next) {
      delay = Math.min(2000, Math.max(50, (next.ts - current.ts) * 1000));
    }
    delay /= replaySpeed;

    const timer = window.setTimeout(() => {
      setReplayCursor(clampReplayCursor(session.replayCursor + 1, session.events.length));
    }, delay);

    return () => {
      window.clearTimeout(timer);
    };
  }, [
    replayPlaying,
    replaySpeed,
    session.events,
    session.mode,
    session.replayCursor,
    setReplayCursor,
  ]);

  useEffect(() => {
    if (session.mode !== 'live') {
      setInterruptPendingRunId(null);
    }
  }, [session.mode]);

  useEffect(() => {
    const availableIds = new Set<string>(displayJourney.stages.map((stage) => stage.id));
    const fallbackStageId = displayJourney.activeStageId
      || displayJourney.lastVisitedStageId
      || displayJourney.stages[0]?.id
      || null;

    if (!session.selectedStageId || !availableIds.has(session.selectedStageId)) {
      if (session.selectedStageId !== fallbackStageId) {
        setSelectedStageId(fallbackStageId);
      }
    }
  }, [
    displayJourney.activeStageId,
    displayJourney.lastVisitedStageId,
    displayJourney.stages,
    session.selectedStageId,
    setSelectedStageId,
  ]);

  useEffect(() => {
    const availableIds = new Set(displayJourney.timeline.map((entry) => entry.id));
    if (session.selectedTimelineId && availableIds.has(session.selectedTimelineId)) {
      return;
    }

    const fallback = latestTimelineForStage(
      displayJourney.timeline,
      (session.selectedStageId as JourneyStageId | null) || currentStageId,
    );
    const nextTimelineId = fallback?.id || null;
    if (session.selectedTimelineId !== nextTimelineId) {
      setSelectedTimelineId(nextTimelineId);
    }
  }, [
    currentStageId,
    displayJourney.timeline,
    session.selectedStageId,
    session.selectedTimelineId,
    setSelectedTimelineId,
  ]);

  const selectedStage = displayJourney.stages.find((stage) => stage.id === session.selectedStageId) || currentStage;
  const selectedTimelineEntry = displayJourney.timeline.find((entry) => entry.id === session.selectedTimelineId)
    || latestTimelineForStage(displayJourney.timeline, selectedStage?.id || null);

  const handleStageSelect = useCallback((stageId: JourneyStageId) => {
    setSelectedStageId(stageId);
    const fallback = latestTimelineForStage(displayJourney.timeline, stageId);
    setSelectedTimelineId(fallback?.id || null);
  }, [displayJourney.timeline, setSelectedStageId, setSelectedTimelineId]);

  const handleTimelineSelect = useCallback((entry: JourneyTimelineEntry) => {
    setSelectedStageId(entry.stageId);
    setSelectedTimelineId(entry.id);
    if (session.mode === 'replay') {
      setReplayPlaying(false);
      setReplayCursor(clampReplayCursor(entry.endSeq + 1, session.events.length));
    }
  }, [
    session.events.length,
    session.mode,
    setReplayCursor,
    setSelectedStageId,
    setSelectedTimelineId,
  ]);

  const handleReplaySeek = useCallback((cursor: number) => {
    setReplayPlaying(false);
    setReplayCursor(clampReplayCursor(cursor, session.events.length));
  }, [session.events.length, setReplayCursor]);

  const handleReplayStep = useCallback((dir: 1 | -1) => {
    setReplayPlaying(false);
    setReplayCursor(clampReplayCursor(session.replayCursor + dir, session.events.length));
  }, [session.events.length, session.replayCursor, setReplayCursor]);

  const handleSelectLive = useCallback(async (runId: string) => {
    if (session.runId === runId && session.mode === 'live') {
      return;
    }

    setReplayPlaying(false);
    setReplaySpeed(1);
    await selectLiveRun(runId);
  }, [selectLiveRun, session.mode, session.runId]);

  const handleSelectReplay = useCallback(async (runId: string) => {
    if (session.runId === runId && session.mode === 'replay') {
      return;
    }

    setReplayPlaying(false);
    setReplaySpeed(1);
    await selectReplayRun(runId);
  }, [selectReplayRun, session.mode, session.runId]);

  const handleStartSolve = useCallback(async (
    problem: Record<string, unknown>,
    config: Record<string, unknown>,
  ) => {
    try {
      const { runId } = await createRun(problem, config);
      const hydrated = await selectLiveRun(runId);
      if (!hydrated) {
        return false;
      }
      setShowProblemPanel(false);
      return true;
    } catch {
      return false;
    }
  }, [selectLiveRun]);

  const handleInterruptRun = useCallback(async () => {
    if (!session.runId || session.mode !== 'live' || interruptPendingRunId === session.runId) {
      return;
    }
    const currentRunId = session.runId;
    setInterruptPendingRunId(currentRunId);
    try {
      await cancelRun(currentRunId);
      const latestSession = sessionStateRef.current;
      if (latestSession.runId === currentRunId && latestSession.mode === 'live') {
        await selectReplayRun(currentRunId);
      } else {
        setInterruptPendingRunId((pending) => (pending === currentRunId ? null : pending));
      }
    } catch {
      setInterruptPendingRunId((pending) => (pending === currentRunId ? null : pending));
    }
  }, [interruptPendingRunId, selectReplayRun, session.mode, session.runId]);

  const handleDeletedRun = useCallback((runId: string) => {
    dropRun(runId);
  }, [dropRun]);

  const currentStageLabel = currentStage?.title || displayJourney.statusStrip.overallStatus;
  const finalStatus = session.runDetail?.finalStatus || canonicalJourney.finalStatus;

  const header = (
    <div className="dashboard-headerStack">
      <SessionBar
        problemName={problemName}
        runId={session.runId}
        mode={session.mode}
        wsStatus={session.wsStatus}
        hydrationStatus={session.hydrationStatus}
        canInterrupt={session.mode === 'live' && session.runId !== null}
        interruptPending={session.runId !== null && interruptPendingRunId === session.runId}
        onInterrupt={() => {
          void handleInterruptRun();
        }}
        onReconnect={() => {
          void reconnect();
        }}
        onResumeLatest={() => {
          void restoreLatestRun();
        }}
      />

      <div className="dashboard-header">
        <div className="dashboard-header__identity">
          <div className="dashboard-header__brand">AlgoPilot</div>
          <div className="dashboard-header__problemRow">
            <h1 className="dashboard-header__problem">{problemName || 'No Active Problem'}</h1>
            <span className={`journey-pill journey-pill--mode journey-pill--mode-${session.mode}`}>
              {session.mode.toUpperCase()}
            </span>
            <span className="journey-pill journey-pill--status">{displayJourney.statusStrip.overallStatus}</span>
          </div>
        </div>

        <div className="dashboard-header__actions">
          <StatsPanel
            artifact={displayArtifacts.finalArtifact}
            events={displayEvents}
            liveProgress={liveProgress}
            mode={session.mode}
            wsStatus={session.wsStatus}
          />
          <button className="dashboard-header__cta" onClick={() => setShowProblemPanel(true)}>
            Start Solve
          </button>
        </div>
      </div>
    </div>
  );

  const main = (
    <div className="dashboard-main">
      <section className="hero-card surface-card">
        <div className="hero-card__text">
          <div className="surface-kicker">Current Run</div>
          <h2 className="hero-card__title">
            {problemName || 'Pick a sample or paste a custom problem to begin'}
          </h2>
          <p className="hero-card__description">{displayJourney.statusStrip.detail}</p>
        </div>
        <div className="hero-card__summary">
          <div className="hero-card__summaryLabel">Journey Progress</div>
          <div className="hero-card__summaryValue">{completedStageCount}/{totalStages}</div>
          <div className="hero-card__progressBar">
            <div
              className="hero-card__progressFill"
              style={{ width: `${totalStages > 0 ? (touchedStageCount / totalStages) * 100 : 0}%` }}
            />
          </div>
          <div className="hero-card__summaryStats">
            <span>{currentStageLabel || 'Waiting'}</span>
            <span>
              {session.mode === 'replay'
                ? `${session.replayCursor}/${session.events.length || 0}`
                : `${session.events.length} events`}
            </span>
          </div>
          <div className="hero-card__summaryHint">{displayJourney.statusStrip.nextHint}</div>
        </div>
      </section>

      <SolveJourneyMap
        stages={displayJourney.stages}
        activeStageId={displayJourney.activeStageId}
        selectedStageId={session.selectedStageId as JourneyStageId | null}
        mode={session.mode}
        onSelect={handleStageSelect}
      />

      <div className="dashboard-progressGrid">
        <LiveProgressPanel progress={liveProgress} />
        <LiveStatusStrip
          status={displayJourney.statusStrip}
          currentStage={currentStage}
          mode={session.mode}
          replayCursor={session.replayCursor}
          replayTotal={session.events.length}
        />
      </div>

      <RunContextCard
        mode={session.mode}
        runId={session.runId}
        problemName={problemName}
        problem={session.runDetail?.problem || null}
        config={session.runDetail?.config || null}
        eventCount={displayEvents.length}
        stageCount={totalStages}
        touchedStageCount={touchedStageCount}
        completedStageCount={completedStageCount}
        currentStageLabel={currentStageLabel}
        replayCursor={session.replayCursor}
        replayTotal={session.events.length}
        finalStatus={finalStatus}
      />

      <FinalSummaryCard
        problemName={problemName}
        finalStatus={finalStatus}
        timeline={canonicalJourney.timeline}
        artifact={canonicalArtifacts.finalArtifact}
      />

      <FailureAnalysisCard analysis={failureAnalysis} />

      <AlgorithmStoryCard
        story={displayArtifacts.finalArtifact?.algorithmVisualization || null}
        mode={session.mode}
        revision={displayArtifacts.finalArtifact?.solution.version || 0}
      />

      <SolveTimeline
        entries={canonicalJourney.timeline}
        progressSeq={progressSeq}
        selectedEntryId={session.selectedTimelineId}
        mode={session.mode}
        onSelect={handleTimelineSelect}
      />

      <EvidenceWorkbench
        stageId={selectedStage?.id || currentStageId || null}
        timelineEntry={selectedTimelineEntry}
        problem={session.runDetail?.problem || null}
        artifacts={displayArtifacts}
      />
    </div>
  );

  const sidebar = (
    <div className="dashboard-sidebar">
      <StageDetailPanel stage={selectedStage} timelineEntry={selectedTimelineEntry} />

      {session.mode === 'replay' && (
        <section className="side-card surface-card">
          <ReplayScrubber
            entries={canonicalJourney.timeline}
            cursor={session.replayCursor}
            total={session.events.length}
            selectedEntryId={session.selectedTimelineId}
            onSeek={handleReplaySeek}
          />
          <div className="side-card__body">
            <PlaybackControls
              playing={replayPlaying}
              speed={replaySpeed}
              onPlay={() => setReplayPlaying(true)}
              onPause={() => setReplayPlaying(false)}
              onStep={handleReplayStep}
              onSpeedChange={setReplaySpeed}
            />
            <p className="side-card__hint">
              The map, timeline, and live progress panels stay synced to the replay cursor.
            </p>
          </div>
        </section>
      )}

      <section className="side-card surface-card">
        <RunList
          onSelectLive={handleSelectLive}
          onSelectReplay={handleSelectReplay}
          activeRunId={session.runId}
          mode={session.mode}
          onDeletedRun={handleDeletedRun}
        />
      </section>
    </div>
  );

  return (
    <>
      <Layout header={header} main={main} sidebar={sidebar} footer={null} />
      {showProblemPanel && (
        <ProblemPanel
          onSubmit={handleStartSolve}
          onClose={() => setShowProblemPanel(false)}
        />
      )}
    </>
  );
}
