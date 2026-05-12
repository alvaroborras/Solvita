/**
 * Solvita TUI design tokens.
 *
 * Aesthetic: "Adversarial Telemetry" — a refined-industrial dark control room
 * watching two agents (codegen vs hacker) duel over a problem.
 *
 * Two hue families only: cool teal (defender) + warm amber (attacker).
 * Parchment off-white text avoids pure-white sterility.
 * No purple gradients. No rounded box-drawing. No green-good/red-bad cliché.
 */
// ─── Palette (truecolor hex; chalk auto-degrades on 8/256-color terminals) ──
export const PALETTE = {
    // Surfaces
    bg: '#0a0a0a', // near-black, slightly warm
    grid: '#2a2a2a', // dot-grid background texture (very dim)
    rule: '#3a3a3a', // section dividers (heavy ──── lines)
    // Text
    text: '#e8e1d3', // parchment off-white, primary readable text
    meta: '#6b6b6b', // tokens / timestamps / problem path
    dim: '#4a4a4a', // disabled / pending phase glyphs
    // Roles
    defender: '#7dd3c0', // cool teal — codegen / abstract / testgen / plan
    attacker: '#f59e0b', // warm amber — hacker
    strike: '#fbbf24', // bright amber — the moment of impact (STRIKE line)
    referee: '#e8e1d3', // parchment — arena setup (abstract/testgen/plan headers)
    // Verdict colors mirror role colors (winner takes verdict color)
    verdictWin: '#7dd3c0', // codegen wins (status: success)
    verdictLose: '#f59e0b', // hacker wins or budget exhausted (max_iterations / failed)
    verdictError: '#dc2626', // hard error — only color allowed to invoke red
};
// ─── Glyph vocabulary ──────────────────────────────────────────────────────
export const GLYPH = {
    // Phase status icons
    done: '◆', // filled diamond — completed
    retry: '◇', // outline diamond — repaired / regressed
    running: '▶', // play — in progress
    idle: '○', // empty — not yet started
    strike: '⚡', // landed strike (hacker found a bug)
    // Bars / fills (left-to-right pass-rate ramp)
    barFull: '█',
    barEighths: ['▏', '▎', '▍', '▌', '▋', '▊', '▉', '█'],
    // Streaming-patch char ramp (reveal animation: ░ → ▒ → ▓ → █)
    rampLight: '░',
    rampMid: '▒',
    rampHeavy: '▓',
    rampSolid: '█',
    // Test pass/fail dots
    testPass: '●',
    testFail: '○',
    // Background dot grid (rendered at PALETTE.grid)
    gridDot: '·',
    // Section rules
    ruleHeavy: '═',
    ruleLight: '─',
    // Strike scar — horizontal line that crosses the gap when hacker lands a hit
    strikeArrow: '⚡──── STRIKE ────',
    // Token sparkline (8 levels of braille for vertical bar columns)
    sparkBars: ['⡀', '⡄', '⡆', '⡇', '⡏', '⡟', '⡿', '⣿'],
};
// ─── Layout constants ──────────────────────────────────────────────────────
export const LAYOUT = {
    // Minimum terminal width before falling back to single-column mode
    dualColumnMinWidth: 100,
    // Heavy rule character density when drawing horizontal section dividers
    ruleSegmentChar: '═',
    // Letter-spacing for capitalised phase headers (renders as "A B S T R A C T")
    letterspaceCap: '  ',
    // Number of token-sparkline columns shown in the header
    sparkColumns: 8,
};
// ─── Letter-spacing helper ─────────────────────────────────────────────────
/**
 * Render an UPPERCASE label with controlled letter spacing.
 *   spaceCaps('STRIKE') → 'S T R I K E'
 * Trailing space is stripped.
 */
export function spaceCaps(s) {
    return s.toUpperCase().split('').join(' ').trimEnd();
}
//# sourceMappingURL=theme.js.map