import type { SolveOptions } from './types.js';
export declare function getProjectRoot(): string;
export declare function detectPythonBin(): string;
interface AppProps {
    /**
     * When non-null, skip interactive input and go straight to solving.
     * Set by `solvita solve <file>` subcommand.
     */
    initialOptions: SolveOptions | null;
    /** Explicit project root override (passed from index.tsx which resolves it). */
    projectRoot?: string;
}
export declare function App({ initialOptions, projectRoot: rootOverride }: AppProps): import("react/jsx-runtime").JSX.Element;
export {};
//# sourceMappingURL=App.d.ts.map