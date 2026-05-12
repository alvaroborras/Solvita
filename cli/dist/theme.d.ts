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
export interface Palette {
    bg: string;
    grid: string;
    rule: string;
    text: string;
    meta: string;
    dim: string;
    defender: string;
    attacker: string;
    strike: string;
    referee: string;
    verdictWin: string;
    verdictLose: string;
    verdictError: string;
}
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
 * Clamp a raw terminal-column count to a usable horizontal budget.
 * - Subtract 2 to leave room for the right-edge cursor / scrollbar
 * - Floor at 40 so very narrow terminals still produce a visible line
 *   (we will downgrade layout to single-column at < 100 anyway)
 */
export declare function safeWidth(rawCols: number | undefined | null): number;
export type ThemeName = 'dark' | 'light';
export declare function detectTheme(): ThemeName;
export declare function getPalette(theme?: ThemeName): Palette;
export declare const PALETTE: Palette;
export declare function spaceCaps(s: string): string;
//# sourceMappingURL=theme.d.ts.map