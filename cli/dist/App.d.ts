import type { SolveOptions } from './types.js';
export declare function getProjectRoot(): string;
export declare function detectPythonBin(): string;
interface AppProps {
    initialOptions: SolveOptions | null;
    projectRoot?: string;
}
export declare function App({ initialOptions, projectRoot: rootOverride }: AppProps): import("react/jsx-runtime").JSX.Element;
export {};
//# sourceMappingURL=App.d.ts.map