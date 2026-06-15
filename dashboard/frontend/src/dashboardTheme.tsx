import { createContext, ReactNode, useContext, useEffect, useMemo, useState } from 'react';

export type DashboardTheme = 'dark' | 'bright';

const THEME_STORAGE_KEY = 'algopilot-dashboard-theme';

interface DashboardThemeContextValue {
  theme: DashboardTheme;
  setTheme: (theme: DashboardTheme) => void;
  toggleTheme: () => void;
}

const DEFAULT_THEME: DashboardThemeContextValue = {
  theme: 'dark',
  setTheme: () => {},
  toggleTheme: () => {},
};

const DashboardThemeContext = createContext<DashboardThemeContextValue>(DEFAULT_THEME);

function readStoredTheme(): DashboardTheme {
  const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
  return stored === 'bright' || stored === 'dark' ? stored : 'dark';
}

export function DashboardThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<DashboardTheme>(() => readStoredTheme());

  useEffect(() => {
    document.documentElement.dataset.dashboardTheme = theme;
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [theme]);

  const value = useMemo<DashboardThemeContextValue>(() => ({
    theme,
    setTheme,
    toggleTheme: () => setTheme((current) => (current === 'dark' ? 'bright' : 'dark')),
  }), [theme]);

  return (
    <DashboardThemeContext.Provider value={value}>
      {children}
    </DashboardThemeContext.Provider>
  );
}

export function useDashboardTheme(): DashboardThemeContextValue {
  return useContext(DashboardThemeContext);
}
