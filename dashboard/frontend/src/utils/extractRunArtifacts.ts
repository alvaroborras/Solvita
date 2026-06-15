import {
  RunArtifacts,
  FinalArtifactSnapshot,
  SolutionSnapshot,
  AlgorithmVisualization,
  AlgorithmStoryStep,
  ArtifactFailureCase,
  ArtifactTestCase,
} from '../types/artifacts';
import { AlgoPilotEvent } from '../types/events';

type PartialFinalArtifactSnapshot = {
  status?: string | null;
  iteration?: number | null;
  llmCalls?: number | null;
  promptTokens?: number | null;
  completionTokens?: number | null;
  algorithmVisualization?: AlgorithmVisualization | null;
  solution?: {
    code?: string;
    version?: number;
    lineCount?: number;
    compilationSuccess?: boolean | null;
    compilationErrors?: string[];
  };
  feedback?: {
    analysis?: string | null;
    errorPattern?: string | null;
    suggestedFixes?: string[];
  };
  tests?: {
    publicTests?: ArtifactTestCase[];
    generatedTests?: ArtifactTestCase[];
    passedTests?: number;
    totalTests?: number;
    passRate?: number;
    fullTestgenCompleted?: boolean;
    trustTiers?: Record<string, number>;
  };
  hack?: {
    result?: string | null;
    passed?: boolean | null;
    round?: number | null;
    failures?: ArtifactFailureCase[];
    generatorFailureKind?: string | null;
    generatorFailureReason?: string | null;
  };
  executionLogTail?: string[];
};

function hasOwn(record: Record<string, unknown>, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(record, key);
}

function normalizeString(value: unknown): string | null {
  if (typeof value !== 'string') {
    return null;
  }
  const normalized = value.trim();
  return normalized.length > 0 ? normalized : null;
}

function normalizeNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function normalizeBoolean(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null;
}

function normalizeStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)) : [];
}

function normalizeSolutionSnapshot(event: AlgoPilotEvent): SolutionSnapshot | null {
  if (event.type !== 'solution_snapshot') return null;
  return {
    version: Number((event as { version?: number }).version || 0),
    code: String((event as { code?: string }).code || ''),
    lineCount: Number((event as { line_count?: number }).line_count || 0),
    mode: typeof (event as { mode?: string }).mode === 'string' ? (event as { mode?: string }).mode : undefined,
    seq: event.seq,
    ts: event.ts,
  };
}

function normalizeFinalArtifact(event: AlgoPilotEvent): PartialFinalArtifactSnapshot | null {
  if (event.type !== 'artifact_snapshot') return null;
  const rawData = ((event as { data?: Record<string, unknown> }).data || {}) as Record<string, unknown>;
  const rawSolution = (rawData.solution || {}) as Record<string, unknown>;
  const rawFeedback = (rawData.feedback || {}) as Record<string, unknown>;
  const rawTests = (rawData.tests || {}) as Record<string, unknown>;
  const rawHack = (rawData.hack || {}) as Record<string, unknown>;
  const snapshot: PartialFinalArtifactSnapshot = {};

  if (hasOwn(rawData, 'status')) snapshot.status = normalizeString(rawData.status);
  if (hasOwn(rawData, 'iteration')) snapshot.iteration = normalizeNumber(rawData.iteration);
  if (hasOwn(rawData, 'llm_calls')) snapshot.llmCalls = normalizeNumber(rawData.llm_calls);
  if (hasOwn(rawData, 'prompt_tokens')) snapshot.promptTokens = normalizeNumber(rawData.prompt_tokens);
  if (hasOwn(rawData, 'completion_tokens')) snapshot.completionTokens = normalizeNumber(rawData.completion_tokens);
  if (hasOwn(rawData, 'algorithm_visualization')) {
    snapshot.algorithmVisualization = normalizeAlgorithmVisualization(rawData.algorithm_visualization);
  }

  if (hasOwn(rawData, 'solution')) {
    snapshot.solution = {};
    if (hasOwn(rawSolution, 'code')) snapshot.solution.code = String(rawSolution.code || '');
    if (hasOwn(rawSolution, 'version')) snapshot.solution.version = Number(rawSolution.version || 0);
    if (hasOwn(rawSolution, 'line_count')) snapshot.solution.lineCount = Number(rawSolution.line_count || 0);
    if (hasOwn(rawSolution, 'compilation_success')) {
      snapshot.solution.compilationSuccess = normalizeBoolean(rawSolution.compilation_success);
    }
    if (hasOwn(rawSolution, 'compilation_errors')) {
      snapshot.solution.compilationErrors = normalizeStringArray(rawSolution.compilation_errors);
    }
  }

  if (hasOwn(rawData, 'feedback')) {
    snapshot.feedback = {};
    if (hasOwn(rawFeedback, 'analysis')) snapshot.feedback.analysis = normalizeString(rawFeedback.analysis);
    if (hasOwn(rawFeedback, 'error_pattern')) {
      snapshot.feedback.errorPattern = normalizeString(rawFeedback.error_pattern);
    }
    if (hasOwn(rawFeedback, 'suggested_fixes')) {
      snapshot.feedback.suggestedFixes = normalizeStringArray(rawFeedback.suggested_fixes);
    }
  }

  if (hasOwn(rawData, 'tests')) {
    snapshot.tests = {};
    if (hasOwn(rawTests, 'public_tests')) {
      snapshot.tests.publicTests = Array.isArray(rawTests.public_tests) ? rawTests.public_tests as ArtifactTestCase[] : [];
    }
    if (hasOwn(rawTests, 'generated_tests')) {
      snapshot.tests.generatedTests = Array.isArray(rawTests.generated_tests)
        ? rawTests.generated_tests as ArtifactTestCase[]
        : [];
    }
    if (hasOwn(rawTests, 'passed_tests')) snapshot.tests.passedTests = Number(rawTests.passed_tests || 0);
    if (hasOwn(rawTests, 'total_tests')) snapshot.tests.totalTests = Number(rawTests.total_tests || 0);
    if (hasOwn(rawTests, 'pass_rate')) snapshot.tests.passRate = Number(rawTests.pass_rate || 0);
    if (hasOwn(rawTests, 'full_testgen_completed')) {
      snapshot.tests.fullTestgenCompleted = Boolean(rawTests.full_testgen_completed);
    }
    if (hasOwn(rawTests, 'trust_tiers')) {
      snapshot.tests.trustTiers = (rawTests.trust_tiers || {}) as Record<string, number>;
    }
  }

  if (hasOwn(rawData, 'hack')) {
    snapshot.hack = {};
    if (hasOwn(rawHack, 'result')) snapshot.hack.result = normalizeString(rawHack.result);
    if (hasOwn(rawHack, 'passed')) snapshot.hack.passed = normalizeBoolean(rawHack.passed);
    if (hasOwn(rawHack, 'round')) snapshot.hack.round = normalizeNumber(rawHack.round);
    if (hasOwn(rawHack, 'failures')) {
      snapshot.hack.failures = Array.isArray(rawHack.failures) ? rawHack.failures as ArtifactFailureCase[] : [];
    }
    if (hasOwn(rawHack, 'generator_failure_kind')) {
      snapshot.hack.generatorFailureKind = normalizeString(rawHack.generator_failure_kind);
    }
    if (hasOwn(rawHack, 'generator_failure_reason')) {
      snapshot.hack.generatorFailureReason = normalizeString(rawHack.generator_failure_reason);
    }
  }

  if (hasOwn(rawData, 'execution_log_tail')) {
    snapshot.executionLogTail = normalizeStringArray(rawData.execution_log_tail);
  }

  return snapshot;
}

function createEmptyFinalArtifact(): FinalArtifactSnapshot {
  return {
    status: null,
    iteration: null,
    llmCalls: null,
    promptTokens: null,
    completionTokens: null,
    algorithmVisualization: null,
    solution: {
      code: '',
      version: 0,
      lineCount: 0,
      compilationSuccess: null,
      compilationErrors: [],
    },
    feedback: {
      analysis: null,
      errorPattern: null,
      suggestedFixes: [],
    },
    tests: {
      publicTests: [],
      generatedTests: [],
      passedTests: 0,
      totalTests: 0,
      passRate: 0,
      fullTestgenCompleted: false,
      trustTiers: {},
    },
    hack: {
      result: null,
      passed: null,
      round: null,
      failures: [],
      generatorFailureKind: null,
      generatorFailureReason: null,
    },
    executionLogTail: [],
  };
}

function mergeNullable<T>(previous: T | null, next: T | null | undefined): T | null {
  return next === null || next === undefined ? previous : next;
}

function mergeDefined<T>(previous: T, next: T | undefined): T {
  return next === undefined ? previous : next;
}

function replaceOrClearArray<T>(next: T[] | undefined): T[] {
  return next ?? [];
}

function replaceOrClearMap<T extends Record<string, unknown>>(next: T | undefined): T {
  return next ?? {} as T;
}

function mergeFinalArtifact(
  previous: FinalArtifactSnapshot | null,
  next: PartialFinalArtifactSnapshot | null,
): FinalArtifactSnapshot | null {
  if (!next) return previous;
  const base = previous ?? createEmptyFinalArtifact();

  return {
    status: mergeNullable(base.status ?? null, next.status),
    iteration: mergeNullable(base.iteration ?? null, next.iteration),
    llmCalls: mergeNullable(base.llmCalls ?? null, next.llmCalls),
    promptTokens: mergeNullable(base.promptTokens ?? null, next.promptTokens),
    completionTokens: mergeNullable(base.completionTokens ?? null, next.completionTokens),
    algorithmVisualization: mergeNullable(base.algorithmVisualization, next.algorithmVisualization),
    solution: {
      code: mergeDefined(base.solution.code, next.solution?.code),
      version: mergeDefined(base.solution.version, next.solution?.version),
      lineCount: mergeDefined(base.solution.lineCount, next.solution?.lineCount),
      compilationSuccess: mergeNullable(base.solution.compilationSuccess ?? null, next.solution?.compilationSuccess),
      compilationErrors: mergeDefined(base.solution.compilationErrors, next.solution?.compilationErrors),
    },
    feedback: {
      analysis: mergeNullable(base.feedback.analysis ?? null, next.feedback?.analysis),
      errorPattern: mergeNullable(base.feedback.errorPattern ?? null, next.feedback?.errorPattern),
      suggestedFixes: mergeDefined(base.feedback.suggestedFixes, next.feedback?.suggestedFixes),
    },
    tests: {
      publicTests: mergeDefined(base.tests.publicTests, next.tests?.publicTests),
      generatedTests: mergeDefined(base.tests.generatedTests, next.tests?.generatedTests),
      passedTests: mergeDefined(base.tests.passedTests, next.tests?.passedTests),
      totalTests: mergeDefined(base.tests.totalTests, next.tests?.totalTests),
      passRate: mergeDefined(base.tests.passRate, next.tests?.passRate),
      fullTestgenCompleted: mergeDefined(base.tests.fullTestgenCompleted, next.tests?.fullTestgenCompleted),
      trustTiers: replaceOrClearMap(next.tests?.trustTiers),
    },
    hack: {
      result: mergeNullable(base.hack.result ?? null, next.hack?.result),
      passed: mergeNullable(base.hack.passed ?? null, next.hack?.passed),
      round: mergeNullable(base.hack.round ?? null, next.hack?.round),
      failures: replaceOrClearArray(next.hack?.failures),
      generatorFailureKind: mergeNullable(base.hack.generatorFailureKind ?? null, next.hack?.generatorFailureKind),
      generatorFailureReason: mergeNullable(base.hack.generatorFailureReason ?? null, next.hack?.generatorFailureReason),
    },
    executionLogTail: replaceOrClearArray(next.executionLogTail),
  };
}

function normalizeAlgorithmVisualization(raw: unknown): AlgorithmVisualization | null {
  if (!raw || typeof raw !== 'object') return null;
  const data = raw as Record<string, unknown>;
  const steps = Array.isArray(data.steps) ? data.steps : [];

  return {
    supported: Boolean(data.supported),
    family: normalizeFamily(data.family),
    mode: String(data.mode || 'teaching'),
    sampleSource: String(data.sample_source || ''),
    sampleFocus: String(data.sample_focus || ''),
    sampleInput: String(data.sample_input || ''),
    sampleOutput: String(data.sample_output || ''),
    title: String(data.title || ''),
    summary: String(data.summary || ''),
    steps: steps
      .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object')
      .map(normalizeStoryStep),
    liveCursor: typeof data.live_cursor === 'number' ? data.live_cursor : null,
    liveAutoplay: typeof data.live_autoplay === 'boolean' ? data.live_autoplay : null,
    traceSource: typeof data.trace_source === 'string' ? data.trace_source : null,
    sampleValidated: typeof data.sample_validated === 'boolean' ? data.sample_validated : null,
    sampleMatches: typeof data.sample_matches === 'boolean' ? data.sample_matches : null,
    validationNote: typeof data.validation_note === 'string' ? data.validation_note : null,
    fallbackText: String(data.fallback_text || ''),
  };
}

function normalizeFamily(raw: unknown): AlgorithmVisualization['family'] {
  const value = String(raw || 'unsupported');
  if (value === 'bfs' || value === 'dfs_recursion' || value === 'basic_dp' || value === 'two_pointers' || value === 'sliding_window' || value === 'binary_search' || value === 'prefix_sum' || value === 'union_find' || value === 'topological_sort' || value === 'greedy_interval' || value === 'monotonic_stack' || value === 'unsupported') {
    return value;
  }
  return 'unsupported';
}

function normalizeStoryStep(raw: Record<string, unknown>): AlgorithmStoryStep {
  return {
    step: Number(raw.step || 0),
    label: String(raw.label || ''),
    caption: String(raw.caption || ''),
    state: (raw.state && typeof raw.state === 'object' ? raw.state : {}) as Record<string, unknown>,
  };
}

export function extractRunArtifacts(events: AlgoPilotEvent[]): RunArtifacts {
  const solutionSnapshots = events
    .map(normalizeSolutionSnapshot)
    .filter((snapshot): snapshot is SolutionSnapshot => snapshot !== null);

  let finalArtifact: FinalArtifactSnapshot | null = null;
  for (const event of events) {
    const maybeArtifact = normalizeFinalArtifact(event);
    if (maybeArtifact) {
      finalArtifact = mergeFinalArtifact(finalArtifact, maybeArtifact);
    }
  }

  return {
    solutionSnapshots,
    finalArtifact,
  };
}
