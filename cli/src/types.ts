// ─── Python → Node.js NDJSON event types ─────────────────────────────────────
// Each event is a JSON object emitted by src/events.py (one per stdout line).

export interface SolveStartEvent {
  type: 'solve_start';
  problem_id: string;
  max_iterations: number;
}

export interface PhaseStartEvent {
  type: 'phase_start';
  phase: string;
  label: string;
}

export interface PhaseAbstractData {
  tags: string[];
  confidence: number;
}

export interface PhaseTestgenData {
  test_count: number;
}

export interface PhaseSolverData {
  algorithm: string;
}

export interface PhaseCodegenData {
  iteration: number;
  compile_success: boolean;
  passed: number;
  total: number;
  pass_rate: number;
}

export interface PhaseHackerData {
  hack_passed: boolean;
  hack_round: number;
  // Present only when hack_passed=false (bug found)
  failure_type?: string;
  failing_input_head?: string;
  expected_head?: string;
  actual_head?: string;
  details?: string;
}

export type PhaseData =
  | PhaseAbstractData
  | PhaseTestgenData
  | PhaseSolverData
  | PhaseCodegenData
  | PhaseHackerData
  | Record<string, unknown>;

export interface PhaseDoneEvent {
  type: 'phase_done';
  phase: string;
  label: string;
  data: PhaseData;
}

export interface FinalEvent {
  type: 'final';
  status: string;
  iterations: number;
  llm_calls: number;
  passed: number;
  total: number;
  pass_rate: number;
  prompt_tokens: number;
  completion_tokens: number;
}

export interface SolutionSavedEvent {
  type: 'solution_saved';
  path: string;
}

export interface ErrorEvent {
  type: 'error';
  message: string;
}

export interface TokenSampleEvent {
  type: 'token_sample';
  prompt_tokens: number;
  completion_tokens: number;
  total: number;
}

export type SolvitaEvent =
  | SolveStartEvent
  | PhaseStartEvent
  | PhaseDoneEvent
  | FinalEvent
  | SolutionSavedEvent
  | ErrorEvent
  | TokenSampleEvent;

// ─── CLI internal state ──────────────────────────────────────────────────────

export type PhaseStatus = 'pending' | 'running' | 'done' | 'error';

export interface PhaseState {
  key: string;
  label: string;
  status: PhaseStatus;
  detail: string;
}

// ─── Adversarial-telemetry split state ──────────────────────────────────────
// Phases are routed by key into one of three buckets:
//   arena    — abstract / testgen / solver_skill_plan (pre-fight setup)
//   defender — codegen iterations (one entry per iteration)
//   attacker — hacker rounds (one entry per round)
// Strikes are emitted when a hacker round resolves with hack_passed=false:
// they're permanent scars rendered horizontally across the gap.

export interface ArenaItem {
  key: 'abstract_phase' | 'testgen_phase' | 'solver_skill_plan';
  label: string;
  status: PhaseStatus;
  // Free-form fields surfaced from PhaseDoneEvent.data
  tags?: string[];
  confidence?: number;
  testCount?: number;
  algorithm?: string;
}

export interface DefenderIter {
  iteration: number;          // 0-based as emitted by unified_check
  status: PhaseStatus;        // running while codegen_phase is open, done after unified_check
  compileSuccess?: boolean;
  passed?: number;
  total?: number;
  passRate?: number;          // 0..1
  patched?: boolean;          // true on iter > 0 (means this row replaced an earlier)
}

export interface AttackerRound {
  round: number;              // 1-based hack_round
  status: PhaseStatus;
  landed?: boolean;           // true when hack_passed=false (bug found)
}

export interface Strike {
  round: number;              // attacker round that produced the strike
  defenderIter: number;       // most-recent codegen iter at time of strike
  failureType?: string;       // e.g. "WA", "TLE", "RE", "OUTPUT_MISMATCH"
  failingInputHead?: string;  // truncated to ~160 chars by backend
  expectedHead?: string;
  actualHead?: string;
  details?: string;
}

export interface SolverState {
  // Legacy flat list (kept for backward compatibility with existing PhaseRow)
  phases: PhaseState[];

  // Adversarial-telemetry routed buckets
  arena: ArenaItem[];
  defender: DefenderIter[];
  attacker: AttackerRound[];
  strikes: Strike[];

  // Termination
  finalEvent: FinalEvent | null;
  solutionPath: string | null;
  errorMessage: string | null;
  running: boolean;

  // Run-level meta (populated as events arrive)
  problemId: string | null;
  maxIterations: number | null;
  startedAt: number;          // epoch ms; for `t+ MM:SS` clock in header

  // Token timeline (sampled at every phase_done; used for header sparkline)
  tokenSamples: number[];     // running approximate cumulative tokens
}

// ─── CLI options passed from commander ───────────────────────────────────────

export interface SolveOptions {
  /** Absolute path to project root (where main.py lives) */
  projectRoot: string;
  /** Path to the problem JSON file */
  inputFile: string;
  /** Output .cpp path */
  output: string;
  /** Max LLM refinement iterations */
  maxIterations: number;
  /** Python executable name ('python' | 'python3') */
  pythonBin: string;
}
