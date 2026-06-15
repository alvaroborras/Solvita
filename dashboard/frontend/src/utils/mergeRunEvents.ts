import type { AlgoPilotEvent } from '../types/events';

export function mergeRunEvents(existing: AlgoPilotEvent[], incoming: AlgoPilotEvent[]): AlgoPilotEvent[] {
  const eventsBySeq = new Map<number, AlgoPilotEvent>();

  for (const event of existing) {
    eventsBySeq.set(event.seq, event);
  }

  for (const event of incoming) {
    eventsBySeq.set(event.seq, event);
  }

  return [...eventsBySeq.entries()]
    .sort(([leftSeq], [rightSeq]) => leftSeq - rightSeq)
    .map(([, event]) => event);
}
