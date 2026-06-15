export interface ArtifactTestCase {
  input?: string;
  output?: string;
  expected_output?: string;
  type?: string;
  trust_tier?: string;
  description?: string;
}

export interface ArtifactFailureCase {
  input?: string;
  input_text?: string;
  expected?: string;
  expected_output?: string;
  output?: string;
  actual_output?: string;
  details?: string;
  stderr?: string;
  failure_type?: string;
  source_type?: string;
}

export interface SolutionSnapshot {
  version: number;
  code: string;
  lineCount: number;
  mode?: string;
  seq: number;
  ts: number;
}

export interface AlgorithmStoryStep {
  step: number;
  label: string;
  caption: string;
  state: Record<string, unknown>;
}

export interface AlgorithmVisualization {
  supported: boolean;
  family: 'bfs' | 'dfs_recursion' | 'basic_dp' | 'two_pointers' | 'sliding_window' | 'binary_search' | 'prefix_sum' | 'union_find' | 'topological_sort' | 'greedy_interval' | 'monotonic_stack' | 'unsupported';
  mode: string;
  sampleSource: string;
  sampleFocus: string;
  sampleInput: string;
  sampleOutput: string;
  title: string;
  summary: string;
  steps: AlgorithmStoryStep[];
  liveCursor?: number | null;
  liveAutoplay?: boolean | null;
  traceSource?: string | null;
  sampleValidated?: boolean | null;
  sampleMatches?: boolean | null;
  validationNote?: string | null;
  fallbackText: string;
}

export interface FinalArtifactSnapshot {
  status?: string | null;
  iteration?: number | null;
  llmCalls?: number | null;
  promptTokens?: number | null;
  completionTokens?: number | null;
  algorithmVisualization: AlgorithmVisualization | null;
  solution: {
    code: string;
    version: number;
    lineCount: number;
    compilationSuccess?: boolean | null;
    compilationErrors: string[];
  };
  feedback: {
    analysis?: string | null;
    errorPattern?: string | null;
    suggestedFixes: string[];
  };
  tests: {
    publicTests: ArtifactTestCase[];
    generatedTests: ArtifactTestCase[];
    passedTests: number;
    totalTests: number;
    passRate: number;
    fullTestgenCompleted: boolean;
    trustTiers: Record<string, number>;
  };
  hack: {
    result?: string | null;
    passed?: boolean | null;
    round?: number | null;
    failures: ArtifactFailureCase[];
    generatorFailureKind?: string | null;
    generatorFailureReason?: string | null;
  };
  executionLogTail: string[];
}

export interface RunArtifacts {
  solutionSnapshots: SolutionSnapshot[];
  finalArtifact: FinalArtifactSnapshot | null;
}
