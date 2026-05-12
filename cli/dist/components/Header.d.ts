interface HeaderProps {
    problemId: string | null;
    modelLabel?: string;
    startedAt: number;
    tokens: number;
    cost: number | null;
    width: number;
    platformWarning?: boolean;
}
export declare function Header({ problemId, modelLabel, startedAt, tokens, cost, width, platformWarning, }: HeaderProps): import("react/jsx-runtime").JSX.Element;
export {};
//# sourceMappingURL=Header.d.ts.map