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
export declare const PALETTE: {
    readonly bg: "#0a0a0a";
    readonly grid: "#2a2a2a";
    readonly rule: "#3a3a3a";
    readonly text: "#e8e1d3";
    readonly meta: "#6b6b6b";
    readonly dim: "#4a4a4a";
    readonly defender: "#7dd3c0";
    readonly attacker: "#f59e0b";
    readonly strike: "#fbbf24";
    readonly referee: "#e8e1d3";
    readonly verdictWin: "#7dd3c0";
    readonly verdictLose: "#f59e0b";
    readonly verdictError: "#dc2626";
};
export declare const GLYPH: {
    readonly done: "◆";
    readonly retry: "◇";
    readonly running: "▶";
    readonly idle: "○";
    readonly strike: "⚡";
    readonly barFull: "█";
    readonly barEighths: readonly ["▏", "▎", "▍", "▌", "▋", "▊", "▉", "█"];
    readonly rampLight: "░";
    readonly rampMid: "▒";
    readonly rampHeavy: "▓";
    readonly rampSolid: "█";
    readonly testPass: "●";
    readonly testFail: "○";
    readonly gridDot: "·";
    readonly ruleHeavy: "═";
    readonly ruleLight: "─";
    readonly strikeArrow: "⚡──── STRIKE ────";
    readonly sparkBars: readonly ["⡀", "⡄", "⡆", "⡇", "⡏", "⡟", "⡿", "⣿"];
};
export declare const LAYOUT: {
    readonly dualColumnMinWidth: 100;
    readonly ruleSegmentChar: "═";
    readonly letterspaceCap: "  ";
    readonly sparkColumns: 8;
};
/**
 * Render an UPPERCASE label with controlled letter spacing.
 *   spaceCaps('STRIKE') → 'S T R I K E'
 * Trailing space is stripped.
 */
export declare function spaceCaps(s: string): string;
//# sourceMappingURL=theme.d.ts.map