export type JourneyStageId =
  | 'read_problem'
  | 'full_testgen'
  | 'codegen'
  | 'hack';

export type JourneyStageStatus =
  | 'waiting'
  | 'active'
  | 'completed'
  | 'skipped'
  | 'repairing'
  | 'failed';

export type JourneyBeatStatus =
  | 'active'
  | 'completed'
  | 'repairing'
  | 'failed'
  | 'skipped';

export interface JourneyStageMeta {
  id: JourneyStageId;
  order: number;
  title: string;
  badge: string;
  shortDescription: string;
  what: string;
  why: string;
}

export interface JourneyStep {
  id: string;
  label: string;
  summary: string;
  status: 'active' | 'completed' | 'warning' | 'failed';
  ts: number;
  seq: number;
}

export interface JourneyTimelineEntry {
  id: string;
  stageId: JourneyStageId;
  visit: number;
  title: string;
  summary: string;
  status: JourneyBeatStatus;
  startedAt: number;
  endedAt: number;
  startSeq: number;
  endSeq: number;
  steps: JourneyStep[];
  evidence: string[];
  why: string[];
}

export interface JourneyStageCard extends JourneyStageMeta {
  status: JourneyStageStatus;
  visits: number;
  startedAt?: number;
  completedAt?: number;
  summary: string;
  evidence: string[];
  whyNotes: string[];
  latestVisit?: number;
  latestTimelineId?: string;
  steps: JourneyStep[];
}

export interface JourneyStatusStrip {
  overallStatus: string;
  headline: string;
  detail: string;
  nextHint: string;
}

export interface SolveJourney {
  activeStageId: JourneyStageId | null;
  lastVisitedStageId: JourneyStageId | null;
  finalStatus: string | null;
  stages: JourneyStageCard[];
  timeline: JourneyTimelineEntry[];
  statusStrip: JourneyStatusStrip;
}
