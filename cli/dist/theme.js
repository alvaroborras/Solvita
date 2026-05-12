/**
 * Solvita TUI design tokens.
 *
 * Aesthetic: "Adversarial Telemetry" — a refined-industrial control room
 * watching two agents (codegen vs hacker) duel over a problem.
 *
 * Two hue families only: cool teal (defender) + warm amber (attacker).
 * No purple gradients. No green-good/red-bad cliché.
 *
 * Adapts to light or dark terminals via getPalette() — see bottom of file.
 */
// ─── Dark theme (default) ──────────────────────────────────────────────────
// All foreground tiers tested ≥ 4.5:1 contrast on bg #0a0a0a (WCAG AA).
const DARK = {
    bg: '#0a0a0a',
    grid: '#2a2a2a', // 1.5:1 — decorative only, never rendered as text
    rule: '#3a3a3a', // dividers; readable as line work
    text: '#e8e1d3', // 13.8:1 — parchment off-white, primary
    meta: '#8a8a8a', // 5.7:1 — bumped from #6b6b6b for AA compliance
    dim: '#5a5a5a', // 2.7:1 — pending glyphs only
    defender: '#7dd3c0', // 9.5:1 — cool teal
    attacker: '#f59e0b', // 7.6:1 — warm amber
    strike: '#fbbf24', // 9.1:1 — bright impact amber
    referee: '#e8e1d3', // matches text — neutral
    verdictWin: '#7dd3c0',
    verdictLose: '#f59e0b',
    verdictError: '#ef4444', // 5.4:1 — only place red is allowed
};
// ─── Light theme ───────────────────────────────────────────────────────────
// All foreground tiers tested ≥ 4.5:1 contrast on bg #fafaf7 (WCAG AA).
const LIGHT = {
    bg: '#fafaf7',
    grid: '#e0ddd5', // 1.2:1 — decorative
    rule: '#bdb9af', // dividers
    text: '#1a1a1a', // 16.0:1
    meta: '#525252', // 7.4:1
    dim: '#9b9b9b', // 2.8:1 — pending glyphs only
    defender: '#0d7d6f', // 5.6:1 — darker teal so it pops on light
    attacker: '#b45309', // 5.4:1 — darker amber
    strike: '#c2410c', // 6.3:1 — burnt orange for impact
    referee: '#1a1a1a',
    verdictWin: '#0d7d6f',
    verdictLose: '#b45309',
    verdictError: '#b91c1c', // 7.0:1
};
// ─── Glyph vocabulary (theme-independent) ──────────────────────────────────
export const GLYPH = {
    done: '◆',
    retry: '◇',
    running: '▶',
    idle: '○',
    strike: '⚡',
    barFull: '█',
    barEighths: ['▏', '▎', '▍', '▌', '▋', '▊', '▉', '█'],
    rampLight: '░',
    rampMid: '▒',
    rampHeavy: '▓',
    rampSolid: '█',
    testPass: '●',
    testFail: '○',
    gridDot: '·',
    ruleHeavy: '═',
    ruleLight: '─',
    strikeArrow: '⚡──── STRIKE ────',
    sparkBars: ['⡀', '⡄', '⡆', '⡇', '⡏', '⡟', '⡿', '⣿'],
};
// ─── Layout constants ──────────────────────────────────────────────────────
export const LAYOUT = {
    dualColumnMinWidth: 100,
    ruleSegmentChar: '═',
    letterspaceCap: '  ',
    sparkColumns: 8,
};
export function detectTheme() {
    const explicit = (process.env.SOLVITA_THEME ?? '').toLowerCase().trim();
    if (explicit === 'light')
        return 'light';
    if (explicit === 'dark')
        return 'dark';
    const cfgbg = process.env.COLORFGBG;
    if (cfgbg) {
        // "fg;bg" or "fg;default;bg"
        const parts = cfgbg.split(';');
        const bgRaw = parts[parts.length - 1];
        const bg = parseInt(bgRaw ?? '', 10);
        if (Number.isFinite(bg)) {
            // 0..6 are "dark" ANSI bg colors; 7..15 (and especially 15 = white) are light
            return bg >= 9 ? 'light' : 'dark';
        }
    }
    return 'dark';
}
export function getPalette(theme) {
    return (theme ?? detectTheme()) === 'light' ? LIGHT : DARK;
}
// Backwards compatibility: existing components import { PALETTE } directly.
// We resolve once at module load — if the user changes SOLVITA_THEME mid-run
// they need a restart, which is fine.
export const PALETTE = getPalette();
// ─── Letter-spacing helper ─────────────────────────────────────────────────
export function spaceCaps(s) {
    return s.toUpperCase().split('').join(' ').trimEnd();
}
//# sourceMappingURL=theme.js.map