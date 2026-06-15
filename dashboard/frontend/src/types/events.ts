export type EventType =
  | 'solve_start'
  | 'phase_start'
  | 'phase_done'
  | 'token_sample'
  | 'node_enter'
  | 'node_exit'
  | 'solution_snapshot'
  | 'artifact_snapshot'
  | 'final'
  | 'solution_saved'
  | 'run_complete'
  | 'error';

export interface BaseEvent {
  type: EventType;
  ts: number;
  seq: number;
}

export interface SolveStartEvent extends BaseEvent {
  type: 'solve_start';
  problem_name?: string;
  problem_id?: string;
  max_iterations?: number;
}

export interface PhaseStartEvent extends BaseEvent {
  type: 'phase_start';
  phase: string;
}

export interface PhaseDoneEvent extends BaseEvent {
  type: 'phase_done';
  phase: string;
  data: Record<string, unknown>;
}

export interface TokenSampleEvent extends BaseEvent {
  type: 'token_sample';
  model?: string;
  input_tokens?: number;
  output_tokens?: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  total?: number;
}

export interface NodeEnterEvent extends BaseEvent {
  type: 'node_enter';
  node_id: string;
  subgraph: string;
}

export interface NodeExitEvent extends BaseEvent {
  type: 'node_exit';
  node_id: string;
  subgraph: string;
  routing_decision: string;
}

export interface FinalEvent extends BaseEvent {
  type: 'final';
  accepted?: boolean;
  status?: string;
  pass_rate?: number;
  iterations?: number;
  total_tokens?: number;
  llm_calls?: number;
  passed?: number;
  total?: number;
  prompt_tokens?: number;
  completion_tokens?: number;
}

export interface SolutionSnapshotEvent extends BaseEvent {
  type: 'solution_snapshot';
  version?: number;
  code?: string;
  line_count?: number;
  mode?: string;
  stage?: string;
}

export interface ArtifactSnapshotEvent extends BaseEvent {
  type: 'artifact_snapshot';
  data?: Record<string, unknown>;
}

export interface ErrorEvent extends BaseEvent {
  type: 'error';
  message: string;
}

export type AlgoPilotEvent =
  | SolveStartEvent
  | PhaseStartEvent
  | PhaseDoneEvent
  | TokenSampleEvent
  | NodeEnterEvent
  | NodeExitEvent
  | SolutionSnapshotEvent
  | ArtifactSnapshotEvent
  | FinalEvent
  | ErrorEvent
  | (BaseEvent & Record<string, unknown>);
