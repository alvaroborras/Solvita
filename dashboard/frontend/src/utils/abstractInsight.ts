import type { AlgoPilotEvent } from '../types/events';

export interface AbstractInsight {
  tags: string[];
  confidence: number | null;
}

function normalizeTags(raw: unknown): string[] {
  if (!Array.isArray(raw)) return [];
  const seen = new Set<string>();
  const tags: string[] = [];

  for (const item of raw) {
    const tag = String(item || '').trim();
    if (!tag || seen.has(tag)) continue;
    seen.add(tag);
    tags.push(tag);
  }

  return tags;
}

function normalizeConfidence(raw: unknown): number | null {
  if (typeof raw !== 'number' || !Number.isFinite(raw)) return null;
  return Math.max(0, Math.min(1, raw));
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

export function extractAbstractInsight(events: AlgoPilotEvent[]): AbstractInsight | null {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];
    if (event.type !== 'phase_done' || event.phase !== 'abstract_phase') continue;

    const data = asRecord(event.data);
    const tags = normalizeTags(data.tags);
    const confidence = normalizeConfidence(data.confidence);
    if (tags.length === 0 && confidence === null) return null;

    return { tags, confidence };
  }

  return null;
}
