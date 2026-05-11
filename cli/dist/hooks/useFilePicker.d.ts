export interface FileEntry {
    label: string;
    fullPath: string;
}
/**
 * Scan the ``data/problem/`` directory inside the project root and return
 * a list of selectable problem JSON files.
 */
export declare function useFilePicker(projectRoot: string): {
    entries: FileEntry[];
    selectedIndex: number;
    selected: FileEntry;
    selectNext: () => void;
    selectPrev: () => void;
};
//# sourceMappingURL=useFilePicker.d.ts.map