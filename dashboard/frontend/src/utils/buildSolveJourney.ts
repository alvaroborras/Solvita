import { AlgoPilotEvent } from '../types/events';
import {
  JourneyBeatStatus,
  JourneyStageCard,
  JourneyStageId,
  JourneyStageMeta,
  JourneyStageStatus,
  JourneyStatusStrip,
  JourneyStep,
  JourneyTimelineEntry,
  SolveJourney,
} from '../types/journey';

const STAGE_META: JourneyStageMeta[] = [
  {
    id: 'read_problem',
    order: 0,
    title: 'Read Problem',
    badge: '01',
    shortDescription: 'Turn the statement into structured constraints and tags.',
    what: 'The agent compresses the natural-language statement into machine-usable objectives, constraints, and problem tags.',
    why: 'A clean abstraction makes later code generation and checking less brittle.',
  },
  {
    id: 'full_testgen',
    order: 1,
    title: 'Full Testgen',
    badge: '02',
    shortDescription: 'Expand coverage when risk is high or checks ask for more evidence.',
    what: 'The agent generates a wider battery of tests to pressure candidate solutions.',
    why: 'More coverage is useful when the problem looks risky or trust remains low.',
  },
  {
    id: 'codegen',
    order: 2,
    title: 'Codegen',
    badge: '03',
    shortDescription: 'Draft, compile, and run the current solver attempt.',
    what: 'This stage writes code, compiles it, runs it on available tests, and learns from failures.',
    why: 'The agent needs a concrete solver candidate before it can verify or attack it.',
  },
  {
    id: 'hack',
    order: 3,
    title: 'Hack',
    badge: '04',
    shortDescription: 'Try to break the accepted-looking solution with adversarial inputs.',
    what: 'The agent stress-tests the candidate by searching for hidden counterexamples.',
    why: 'Late-stage breaking is the last chance to catch bugs before declaring success.',
  },
];

const STAGE_META_BY_ID: Record<JourneyStageId, JourneyStageMeta> = Object.fromEntries(
  STAGE_META.map((meta) => [meta.id, meta])
) as Record<JourneyStageId, JourneyStageMeta>;

const PHASE_STAGE_MAP: Record<string, JourneyStageId> = {
  abstract_phase: 'read_problem',
  testgen_phase: 'full_testgen',
  solver_skill_plan: 'codegen',
  codegen_phase: 'codegen',
  hacker_phase: 'hack',
};

const NODE_STAGE_MAP: Record<string, JourneyStageId> = {
  abstract_problem: 'read_problem',
  generate_tests: 'full_testgen',
  solver_skill_plan: 'codegen',
  solver_skill_plan_ensemble: 'codegen',
  generate_code: 'codegen',
  compile_code: 'codegen',
  join_ready: 'codegen',
  run_tests: 'codegen',
  update_best_solution: 'codegen',
  unified_check: 'codegen',
  update_plan_memory: 'codegen',
  update_solve_memory: 'codegen',
  update_oracle_memory: 'codegen',
  analyze_feedback: 'codegen',
  restore_best_solution: 'codegen',
  enter_hack_phase: 'hack',
  hack_test: 'hack',
  settle_hacker_memory: 'hack',
};

const STAGE_KIND: Record<JourneyStageId, 'instant' | 'phase'> = {
  read_problem: 'phase',
  full_testgen: 'phase',
  codegen: 'phase',
  hack: 'phase',
};

type MutableTimelineEntry = JourneyTimelineEntry & {
  closed: boolean;
  stageKind: 'instant' | 'phase';
  lastNodeId?: string;
};

export function phaseToStageId(phase: string | undefined): JourneyStageId | null {
  if (!phase) return null;
  return PHASE_STAGE_MAP[phase] || null;
}

export function nodeToStageId(nodeId: string | undefined): JourneyStageId | null {
  if (!nodeId) return null;
  return NODE_STAGE_MAP[nodeId] || null;
}

function stageTitle(stageId: JourneyStageId): string {
  return STAGE_META_BY_ID[stageId].title;
}

function stageKind(stageId: JourneyStageId): 'instant' | 'phase' {
  return STAGE_KIND[stageId];
}

export function nodeLabel(nodeId: string): string {
  const labels: Record<string, string> = {
    abstract_problem: 'Read the statement',
    generate_tests: 'Generate more tests',
    solver_skill_plan: 'Choose a strategy',
    solver_skill_plan_ensemble: 'Compare strategy branches',
    generate_code: 'Draft solver code',
    compile_code: 'Compile the draft',
    join_ready: 'Prepare artifacts',
    run_tests: 'Run available tests',
    update_best_solution: 'Keep the best candidate',
    unified_check: 'Score the attempt',
    update_plan_memory: 'Store planning lessons',
    update_solve_memory: 'Store solving lessons',
    update_oracle_memory: 'Store oracle hints',
    analyze_feedback: 'Analyze failures',
    restore_best_solution: 'Restore best solution',
    enter_hack_phase: 'Promote to hack mode',
    hack_test: 'Try to break the solution',
    settle_hacker_memory: 'Record hack lessons',
  };
  return labels[nodeId] || nodeId.replace(/_/g, ' ');
}

export function nodeSummary(nodeId: string): string {
  const summaries: Record<string, string> = {
    abstract_problem: 'Extracting objective, constraints, and hidden structure.',
    generate_tests: 'Expanding coverage with broader generated examples.',
    solver_skill_plan: 'Choosing an algorithmic direction before coding.',
    solver_skill_plan_ensemble: 'Comparing multiple strategy branches before choosing one.',
    generate_code: 'Writing the current solver draft.',
    compile_code: 'Checking that the latest draft builds cleanly.',
    join_ready: 'Preparing the compiled solver for execution.',
    run_tests: 'Running the current draft against the available suite.',
    update_best_solution: 'Keeping the strongest candidate seen so far.',
    unified_check: 'Summarizing how well the current attempt performed.',
    update_plan_memory: 'Saving planning lessons for future retries.',
    update_solve_memory: 'Saving solution lessons from this attempt.',
    update_oracle_memory: 'Saving feedback for future reasoning.',
    analyze_feedback: 'Turning failed tests into concrete repair hints.',
    restore_best_solution: 'Restoring the best-known candidate before stopping.',
    enter_hack_phase: 'Moving the candidate into adversarial stress testing.',
    hack_test: 'Trying to generate a breaking input.',
    settle_hacker_memory: 'Recording what the hacker learned.',
  };
  return summaries[nodeId] || 'Processing this step.';
}

function formatPct(value: number | undefined): string {
  const pct = Math.max(0, Math.min(1, value ?? 0));
  return `${Math.round(pct * 100)}%`;
}

function formatTags(raw: unknown): string {
  if (!Array.isArray(raw)) return '';
  const tags = raw.map((item) => String(item || '').trim()).filter(Boolean);
  return tags.slice(0, 3).join(', ');
}

function dedupe(lines: string[]): string[] {
  const seen = new Set<string>();
  const output: string[] = [];
  for (const line of lines) {
    const normalized = line.trim();
    if (!normalized || seen.has(normalized)) continue;
    seen.add(normalized);
    output.push(normalized);
  }
  return output;
}

function closeActiveStep(entry: MutableTimelineEntry, status: JourneyStep['status']): void {
  const last = entry.steps[entry.steps.length - 1];
  if (last && last.status === 'active') {
    last.status = status;
  }
}

function appendStep(
  entry: MutableTimelineEntry,
  event: AlgoPilotEvent,
  label: string,
  summary: string,
  status: JourneyStep['status']
): void {
  const id = `${entry.id}-step-${event.seq}`;
  const last = entry.steps[entry.steps.length - 1];
  if (last && last.label === label && last.summary === summary) {
    last.status = status;
    last.ts = event.ts;
    last.seq = event.seq;
    return;
  }
  closeActiveStep(entry, 'completed');
  entry.steps.push({
    id,
    label,
    summary,
    status,
    ts: event.ts,
    seq: event.seq,
  });
}

function createEntry(stageId: JourneyStageId, visit: number, event: AlgoPilotEvent): MutableTimelineEntry {
  return {
    id: `${stageId}-${visit}`,
    stageId,
    visit,
    title: stageTitle(stageId),
    summary: STAGE_META_BY_ID[stageId].shortDescription,
    status: 'active',
    startedAt: event.ts,
    endedAt: event.ts,
    startSeq: event.seq,
    endSeq: event.seq,
    steps: [],
    evidence: [],
    why: [STAGE_META_BY_ID[stageId].why],
    closed: false,
    stageKind: stageKind(stageId),
  };
}

function closeEntry(
  entry: MutableTimelineEntry,
  event: AlgoPilotEvent,
  status: JourneyBeatStatus,
  summary?: string
): void {
  entry.closed = true;
  entry.status = status;
  entry.endedAt = event.ts;
  entry.endSeq = event.seq;
  if (summary) {
    entry.summary = summary;
  }
  closeActiveStep(entry, status === 'failed' ? 'failed' : status === 'repairing' ? 'warning' : 'completed');
}

function closeOtherOpenEntries(
  openEntries: Map<JourneyStageId, MutableTimelineEntry>,
  nextStageId: JourneyStageId,
  event: AlgoPilotEvent
): void {
  for (const [stageId, entry] of openEntries.entries()) {
    if (stageId === nextStageId || entry.closed) continue;
    closeEntry(entry, event, 'completed');
    openEntries.delete(stageId);
  }
}

function startOrReuseEntry(
  stageId: JourneyStageId,
  event: AlgoPilotEvent,
  timeline: MutableTimelineEntry[],
  openEntries: Map<JourneyStageId, MutableTimelineEntry>,
  visitCounts: Record<JourneyStageId, number>
): MutableTimelineEntry {
  const existing = openEntries.get(stageId);
  if (existing && !existing.closed) {
    existing.endedAt = event.ts;
    existing.endSeq = event.seq;
    return existing;
  }
  visitCounts[stageId] += 1;
  const entry = createEntry(stageId, visitCounts[stageId], event);
  timeline.push(entry);
  openEntries.set(stageId, entry);
  return entry;
}

function phaseDoneSummary(stageId: JourneyStageId, event: AlgoPilotEvent, visit: number): string {
  const phase = String((event as { phase?: string }).phase || '');
  const data = ((event as { data?: Record<string, unknown> }).data || {}) as Record<string, unknown>;
  if (phase === 'solver_skill_plan') {
    return 'Locked in a strategy and prepared to write the solver.';
  }
  if (stageId === 'read_problem') {
    const tags = formatTags(data.tags);
    const confidence = typeof data.confidence === 'number' ? `${Math.round((data.confidence as number) * 100)}%` : '';
    if (tags && confidence) return `Mapped the problem to ${tags} with ${confidence} abstraction confidence.`;
    if (tags) return `Mapped the problem around ${tags}.`;
    return 'Converted the statement into a structured internal problem model.';
  }
  if (stageId === 'full_testgen') {
    const testCount = Number(data.test_count || 0);
    if (testCount > 0) {
      return visit > 1
        ? `Expanded coverage with ${testCount} newly generated tests after additional risk was detected.`
        : `Generated ${testCount} broader tests before trusting the solver.`;
    }
    return 'Finished widening the test suite.';
  }
  if (stageId === 'codegen') {
    const total = Number(data.total || 0);
    const passed = Number(data.passed || 0);
    const passRate = typeof data.pass_rate === 'number' ? (data.pass_rate as number) : total > 0 ? passed / total : 0;
    const compileSuccess = Boolean(data.compile_success ?? true);
    if (!compileSuccess) {
      return `Attempt ${visit} failed to compile cleanly and needs repair.`;
    }
    if (total > 0) {
      return `Attempt ${visit} passed ${passed} of ${total} tests (${formatPct(passRate)}).`;
    }
    return `Finished codegen attempt ${visit}.`;
  }
  if (stageId === 'hack') {
    const hackPassed = Boolean(data.hack_passed);
    const round = Number(data.hack_round || visit);
    if (hackPassed) {
      return `Hack round ${round} did not find a breaking input.`;
    }
    return `Hack round ${round} found a breaking case and sent the solver back for repair.`;
  }
  return STAGE_META_BY_ID[stageId as JourneyStageId].shortDescription;
}

function phaseDoneEvidence(stageId: JourneyStageId, event: AlgoPilotEvent, visit: number): string[] {
  const phase = String((event as { phase?: string }).phase || '');
  const data = ((event as { data?: Record<string, unknown> }).data || {}) as Record<string, unknown>;
  if (phase === 'solver_skill_plan') {
    const algorithm = String(data.algorithm || '').trim();
    return algorithm ? [`Planned strategy: ${algorithm}`] : ['A strategy plan was produced before coding.'];
  }
  if (stageId === 'read_problem') {
    const evidence: string[] = [];
    const tags = formatTags(data.tags);
    if (tags) evidence.push(`Tags: ${tags}`);
    if (typeof data.confidence === 'number') {
      evidence.push(`Abstraction confidence: ${Math.round((data.confidence as number) * 100)}%`);
    }
    return evidence;
  }
  if (stageId === 'full_testgen') {
    const testCount = Number(data.test_count || 0);
    return testCount > 0 ? [`Generated tests: ${testCount}`] : [];
  }
  if (stageId === 'codegen') {
    const total = Number(data.total || 0);
    const passed = Number(data.passed || 0);
    const compileSuccess = Boolean(data.compile_success ?? true);
    const passRate = typeof data.pass_rate === 'number' ? (data.pass_rate as number) : total > 0 ? passed / total : 0;
    const evidence = [`Compile status: ${compileSuccess ? 'success' : 'failure'}`];
    if (total > 0) {
      evidence.push(`Visible tests: ${passed}/${total}`);
      evidence.push(`Pass rate: ${formatPct(passRate)}`);
    }
    evidence.push(`Attempt: ${visit}`);
    return evidence;
  }
  if (stageId === 'hack') {
    const round = Number(data.hack_round || visit);
    const evidence = [`Hack round: ${round}`];
    if (data.failure_type) evidence.push(`Failure type: ${String(data.failure_type)}`);
    if (data.failing_input_head) evidence.push(`Input head: ${String(data.failing_input_head)}`);
    if (data.expected_head) evidence.push(`Expected head: ${String(data.expected_head)}`);
    if (data.actual_head) evidence.push(`Actual head: ${String(data.actual_head)}`);
    if (data.details) evidence.push(`Details: ${String(data.details)}`);
    return evidence;
  }
  return [];
}

function phaseDoneWhy(stageId: JourneyStageId, event: AlgoPilotEvent, visit: number): string[] {
  const phase = String((event as { phase?: string }).phase || '');
  const data = ((event as { data?: Record<string, unknown> }).data || {}) as Record<string, unknown>;
  const base = [STAGE_META_BY_ID[stageId].why];
  if (phase === 'solver_skill_plan') {
    base.push('The planner ran before coding to reduce blind trial-and-error.');
    return base;
  }
  if (stageId === 'full_testgen' && visit > 1) {
    base.push('This stage was revisited because earlier evidence was still not strong enough.');
  }
  if (stageId === 'codegen' && visit > 1) {
    base.push('A previous codegen or hack result sent the agent back for repair.');
  }
  if (stageId === 'hack') {
    const hackPassed = Boolean(data.hack_passed);
    if (!hackPassed) base.push('The hacker found a concrete counterexample, so the solver must repair against it.');
  }
  return base;
}

function phaseDoneStatus(stageId: JourneyStageId, event: AlgoPilotEvent): JourneyBeatStatus {
  const phase = String((event as { phase?: string }).phase || '');
  const data = ((event as { data?: Record<string, unknown> }).data || {}) as Record<string, unknown>;
  if (phase === 'solver_skill_plan') {
    return 'active';
  }
  if (stageId === 'hack') {
    const hasFailureSignal = data.hack_passed === false;
    if (hasFailureSignal) return 'repairing';
  }
  return 'completed';
}

function instantSummary(stageId: JourneyStageId, _visit: number): string {
  return STAGE_META_BY_ID[stageId].shortDescription;
}

function instantEvidence(_stageId: JourneyStageId): string[] {
  return [];
}

function instantWhy(stageId: JourneyStageId): string[] {
  return [STAGE_META_BY_ID[stageId].why];
}

function lastDefined<T>(items: T[]): T | undefined {
  return items.length > 0 ? items[items.length - 1] : undefined;
}

function isSuccessfulFinalStatus(status: string): boolean {
  return status === 'success' || status === 'accepted';
}

function computeStageStatus(
  stageId: JourneyStageId,
  entries: JourneyTimelineEntry[],
  activeStageId: JourneyStageId | null,
  finalStatus: string | null,
  maxVisitedOrder: number,
  historyObservedFromStart: boolean
): JourneyStageStatus {
  if (entries.length === 0) {
    if (!historyObservedFromStart) return 'waiting';
    if (finalStatus || STAGE_META_BY_ID[stageId].order < maxVisitedOrder) return 'skipped';
    return 'waiting';
  }

  const last = entries[entries.length - 1];
  if (activeStageId === stageId && !finalStatus) {
    if (last.status === 'repairing') return 'repairing';
    if (stageId === 'codegen' && entries.length > 1) return 'repairing';
    return 'active';
  }

  if (finalStatus && finalStatus !== 'success') {
    if (stageId === 'codegen' && finalStatus === 'max_iterations') return 'failed';
    if (stageId === 'hack' && finalStatus === 'terminal_failure') return 'failed';
  }

  if (last.status === 'failed') return 'failed';
  if (last.status === 'repairing') return 'repairing';
  return 'completed';
}

function finalOutcomeDetail(finalEvent: AlgoPilotEvent): string {
  const raw = finalEvent as Record<string, unknown>;
  const passed = Number(raw.passed || 0);
  const total = Number(raw.total || 0);
  const passRate = typeof raw.pass_rate === 'number' ? (raw.pass_rate as number) : total > 0 ? passed / total : 0;
  if (total > 0) {
    return `Visible test score: ${passed}/${total} (${formatPct(passRate)}).`;
  }
  return 'The workflow has reached a final outcome.';
}

function statusStripForActive(entry: JourneyTimelineEntry): JourneyStatusStrip {
  const meta = STAGE_META_BY_ID[entry.stageId];
  const visitLabel = entry.visit > 1 ? `, pass ${entry.visit}` : '';
  const overallStatus =
    entry.stageId === 'codegen' && entry.visit > 1
      ? 'Repairing'
      : entry.stageId === 'hack'
          ? 'Hacking'
          : 'Running';
  const nextHints: Record<JourneyStageId, string> = {
    read_problem: 'Next: generate stronger tests and move into code generation.',
    full_testgen: 'Next: move into code generation with a stronger test bed.',
    codegen: 'Next: iterate on the draft and then move into adversarial hacking if it passes.',
    hack: 'Next: either declare the solver safe or send a breaking input back for repair.',
  };
  return {
    overallStatus,
    headline: `Now in ${meta.title}${visitLabel}`,
    detail: entry.summary,
    nextHint: nextHints[entry.stageId],
  };
}

function statusStripForFinal(finalEvent: AlgoPilotEvent, timeline: JourneyTimelineEntry[]): JourneyStatusStrip {
  const raw = finalEvent as Record<string, unknown>;
  const status = String(raw.status || 'unknown');
  const lastEntry = lastDefined(timeline);
  if (status === 'success') {
    return {
      overallStatus: 'Accepted',
      headline: lastEntry?.stageId === 'hack'
        ? 'The solver survived visible tests and adversarial breaking.'
        : 'The current candidate was accepted.',
      detail: finalOutcomeDetail(finalEvent),
      nextHint: 'Replay any stage below to inspect how the agent arrived here.',
    };
  }
  if (status === 'max_iterations') {
    return {
      overallStatus: 'Stopped',
      headline: 'The solver ran out of repair budget before it became trustworthy.',
      detail: finalOutcomeDetail(finalEvent),
      nextHint: 'Inspect the latest codegen and hack passes to see where progress stalled.',
    };
  }
  if (status === 'terminal_failure') {
    return {
      overallStatus: 'Failed',
      headline: 'A late-stage hack found a break the solver could not recover from.',
      detail: finalOutcomeDetail(finalEvent),
      nextHint: 'Focus on the final hack rounds and the repair loop that followed them.',
    };
  }
  return {
    overallStatus: 'Finished',
    headline: 'The workflow reached a final state.',
    detail: finalOutcomeDetail(finalEvent),
    nextHint: 'Use the timeline below to inspect the decision path.',
  };
}

function statusStripForIdle(): JourneyStatusStrip {
  return {
    overallStatus: 'Idle',
    headline: 'Pick a problem to watch the solve journey.',
    detail: 'The dashboard is ready for a live run or a replay of a previous solve.',
    nextHint: 'Next: start a solve from the header or open a replay from the run list.',
  };
}

function normalizeTimeline(timeline: MutableTimelineEntry[]): JourneyTimelineEntry[] {
  return timeline.map((entry) => ({
    id: entry.id,
    stageId: entry.stageId,
    visit: entry.visit,
    title: entry.title,
    summary: entry.summary,
    status: entry.status,
    startedAt: entry.startedAt,
    endedAt: entry.endedAt,
    startSeq: entry.startSeq,
    endSeq: entry.endSeq,
    steps: entry.steps,
    evidence: dedupe(entry.evidence),
    why: dedupe(entry.why),
  }));
}

export function buildSolveJourney(events: AlgoPilotEvent[]): SolveJourney {
  const timeline: MutableTimelineEntry[] = [];
  const openEntries = new Map<JourneyStageId, MutableTimelineEntry>();
  const visitCounts = Object.fromEntries(
    STAGE_META.map((meta) => [meta.id, 0])
  ) as Record<JourneyStageId, number>;

  let activeStageId: JourneyStageId | null = null;
  let lastVisitedStageId: JourneyStageId | null = null;
  let finalEvent: AlgoPilotEvent | null = null;
  let lastEvent: AlgoPilotEvent | null = null;

  for (const event of events) {
    lastEvent = event;
    if (event.type === 'final') {
      finalEvent = event;
      continue;
    }
    if (event.type === 'error') {
      continue;
    }

    if (event.type === 'node_enter') {
      const raw = event as { node_id?: string };
      const stageId = nodeToStageId(raw.node_id);
      if (!stageId || !raw.node_id) continue;
      closeOtherOpenEntries(openEntries, stageId, event);
      const entry = startOrReuseEntry(stageId, event, timeline, openEntries, visitCounts);
      activeStageId = stageId;
      lastVisitedStageId = stageId;
      if (entry.stageKind === 'instant') {
        entry.summary = instantSummary(stageId, entry.visit);
        entry.evidence = dedupe([...entry.evidence, ...instantEvidence(stageId)]);
        entry.why = dedupe([...entry.why, ...instantWhy(stageId)]);
      }
      appendStep(entry, event, nodeLabel(raw.node_id), nodeSummary(raw.node_id), 'active');
      if (entry.stageKind !== 'instant') {
        entry.summary = nodeSummary(raw.node_id);
      }
      entry.lastNodeId = raw.node_id;
      entry.endedAt = event.ts;
      entry.endSeq = event.seq;
      continue;
    }

    if (event.type === 'phase_start') {
      const raw = event as { phase?: string; label?: string };
      const stageId = phaseToStageId(raw.phase);
      if (!stageId) continue;
      closeOtherOpenEntries(openEntries, stageId, event);
      const entry = startOrReuseEntry(stageId, event, timeline, openEntries, visitCounts);
      activeStageId = stageId;
      lastVisitedStageId = stageId;
      entry.title = raw.label || stageTitle(stageId);
      appendStep(
        entry,
        event,
        raw.label || stageTitle(stageId),
        raw.phase === 'solver_skill_plan'
          ? 'Using a planner to choose a stronger strategy before coding.'
          : STAGE_META_BY_ID[stageId].shortDescription,
        'active'
      );
      entry.endedAt = event.ts;
      entry.endSeq = event.seq;
      continue;
    }

    if (event.type === 'phase_done') {
      const raw = event as { phase?: string; label?: string; data?: Record<string, unknown> };
      const stageId = phaseToStageId(raw.phase);
      if (!stageId) continue;
      const entry = startOrReuseEntry(stageId, event, timeline, openEntries, visitCounts);
      activeStageId = stageId;
      lastVisitedStageId = stageId;
      const summary = phaseDoneSummary(stageId, event, entry.visit);
      const beatStatus = phaseDoneStatus(stageId, event);
      const stepStatus =
        beatStatus === 'repairing'
          ? 'warning'
          : beatStatus === 'failed'
            ? 'failed'
            : 'completed';
      appendStep(
        entry,
        event,
        raw.label || stageTitle(stageId),
        summary,
        stepStatus
      );
      entry.summary = summary;
      entry.evidence = dedupe([...entry.evidence, ...phaseDoneEvidence(stageId, event, entry.visit)]);
      entry.why = dedupe([...entry.why, ...phaseDoneWhy(stageId, event, entry.visit)]);
      if (raw.phase === 'solver_skill_plan') {
        entry.endedAt = event.ts;
        entry.endSeq = event.seq;
      } else {
        closeEntry(entry, event, beatStatus, summary);
        openEntries.delete(stageId);
      }
      continue;
    }
  }

  if (lastEvent || finalEvent) {
    const closingEvent = finalEvent || lastEvent;
    if (!closingEvent) {
      throw new Error('unreachable');
    }
    for (const [stageId, entry] of openEntries.entries()) {
      if (entry.closed) continue;
      const finalStatus = finalEvent ? String((finalEvent as Record<string, unknown>).status || '') : '';
      const status: JourneyBeatStatus =
        finalStatus
          ? isSuccessfulFinalStatus(finalStatus) || activeStageId !== stageId
            ? 'completed'
            : 'failed'
          : 'active';
      closeEntry(entry, closingEvent, status, entry.summary);
    }
  }

  const normalizedTimeline = normalizeTimeline(timeline);
  if (finalEvent) {
    activeStageId = null;
  }

  const visitedOrders = normalizedTimeline.map((entry) => STAGE_META_BY_ID[entry.stageId].order);
  const maxVisitedOrder = visitedOrders.length > 0 ? Math.max(...visitedOrders) : -1;
  const finalStatus = finalEvent ? String((finalEvent as Record<string, unknown>).status || '') || null : null;
  const historyObservedFromStart = events.some((event) => event.type === 'solve_start');

  const stages: JourneyStageCard[] = STAGE_META.map((meta) => {
    const entries = normalizedTimeline.filter((entry) => entry.stageId === meta.id);
    const latest = lastDefined(entries);
    const status = computeStageStatus(
      meta.id,
      entries,
      activeStageId,
      finalStatus,
      maxVisitedOrder,
      historyObservedFromStart,
    );
    return {
      ...meta,
      status,
      visits: entries.length,
      startedAt: entries[0]?.startedAt,
      completedAt: latest?.endedAt,
      summary: latest?.summary || (status === 'skipped' ? 'Skipped for this run.' : meta.shortDescription),
      evidence: latest?.evidence.length ? latest.evidence : status === 'skipped' ? ['This stage was not needed for this run.'] : [],
      whyNotes: latest?.why.length ? latest.why : [meta.why],
      latestVisit: latest?.visit,
      latestTimelineId: latest?.id,
      steps: latest?.steps || [],
    };
  });

  const statusStrip = finalEvent
    ? statusStripForFinal(finalEvent, normalizedTimeline)
    : activeStageId && normalizedTimeline.length > 0
      ? statusStripForActive(normalizedTimeline[normalizedTimeline.length - 1])
      : statusStripForIdle();

  return {
    activeStageId,
    lastVisitedStageId,
    finalStatus,
    stages,
    timeline: normalizedTimeline,
    statusStrip,
  };
}

export { STAGE_META };
