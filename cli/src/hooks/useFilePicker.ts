import { useState, useCallback } from 'react';
import { readdirSync } from 'fs';
import path from 'path';

export interface FileEntry {
  label: string;
  fullPath: string;
}

/**
 * Scan the ``data/problem/`` directory inside the project root and return
 * a list of selectable problem JSON files.
 */
export function useFilePicker(projectRoot: string) {
  const problemDir = path.join(projectRoot, 'data', 'problem');

  const [entries] = useState<FileEntry[]>(() => {
    try {
      return readdirSync(problemDir)
        .filter((f) => f.endsWith('.json'))
        .sort()
        .map((f) => ({
          label: f.replace(/\.json$/, '').replace(/_/g, ' '),
          fullPath: path.join(problemDir, f),
        }));
    } catch {
      return [];
    }
  });

  const [selectedIndex, setSelectedIndex] = useState(0);

  const selectNext = useCallback(() => {
    setSelectedIndex((i) => Math.min(i + 1, entries.length - 1));
  }, [entries.length]);

  const selectPrev = useCallback(() => {
    setSelectedIndex((i) => Math.max(i - 1, 0));
  }, []);

  const selected = entries[selectedIndex] ?? null;

  return { entries, selectedIndex, selected, selectNext, selectPrev };
}
