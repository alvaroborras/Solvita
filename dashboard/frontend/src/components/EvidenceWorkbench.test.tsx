import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

describe('EvidenceWorkbench styles', () => {
  it('uses theme tokens for code block surfaces instead of a hard-coded dark background', () => {
    const stylesheet = readFileSync(resolve(process.cwd(), 'src/styles/journey.css'), 'utf8');
    const workbenchStart = stylesheet.indexOf('.evidence-workbench');
    const workbenchEnd = stylesheet.indexOf('@media', workbenchStart);
    const workbenchCss = stylesheet.slice(workbenchStart, workbenchEnd);

    expect(workbenchCss).toContain('background: var(--color-evidence-code-bg)');
    expect(workbenchCss).toContain('border: 1px solid var(--color-evidence-code-border)');
    expect(workbenchCss).toContain('color: var(--color-evidence-code-text)');
    expect(workbenchCss).not.toContain('background: rgba(3, 7, 12, 0.95)');
    expect(workbenchCss).not.toContain('color: #d8f3ff');
  });
});
