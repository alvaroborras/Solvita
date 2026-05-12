interface HeaderProps {
    problemId: string | null;
    modelLabel?: string;
    startedAt: number;
    tokens: number;
    /** Cumulative-token timeline; rendered as braille sparkline */
    tokenSamples?: number[];
    cost: number | null;
    width: number;
    platformWarning?: boolean;
}
export declare function Header({ problemId, modelLabel, startedAt, tokens, tokenSamples, cost, width, platformWarning, }: HeaderProps): import("react/jsx-runtime").JSX.Element;
export {};
//# sourceMappingURL=Header.d.ts.map