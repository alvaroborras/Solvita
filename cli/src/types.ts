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

export type SolvitaEvent =
  | SolveStartEvent
  | PhaseStartEvent
  | PhaseDoneEvent
  | FinalEvent
  | SolutionSavedEvent
  | ErrorEvent;

// ─── CLI internal state ──────────────────────────────────────────────────────

export type PhaseStatus = 'pending' | 'running' | 'done' | 'error';

export interface PhaseState {
  key: string;
  label: string;
  status: PhaseStatus;
  detail: string;
}

export interface SolverState {
  phases: PhaseState[];
  finalEvent: FinalEvent | null;
  solutionPath: string | null;
  errorMessage: string | null;
  running: boolean;
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
