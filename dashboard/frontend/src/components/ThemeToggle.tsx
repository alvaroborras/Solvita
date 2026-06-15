import { useDashboardTheme } from '../dashboardTheme';
import { useI18n } from '../i18n';

export default function ThemeToggle() {
  const { theme, toggleTheme } = useDashboardTheme();
  const { t } = useI18n();
  const nextLabel = theme === 'dark' ? t('themeToggleToBright') : t('themeToggleToDark');

  return (
    <button
      type="button"
      className="theme-toggle"
      aria-label={nextLabel}
      onClick={toggleTheme}
    >
      <span className={theme === 'dark' ? 'theme-toggle__option theme-toggle__option--active' : 'theme-toggle__option'}>
        {t('themeDarkShort')}
      </span>
      <span className={theme === 'bright' ? 'theme-toggle__option theme-toggle__option--active' : 'theme-toggle__option'}>
        {t('themeBrightShort')}
      </span>

      <style>{`
        .theme-toggle {
          display: inline-flex;
          align-items: center;
          align-self: center;
          gap: 4px;
          height: 48px;
          padding: 4px;
          border: 1px solid var(--color-border-subtle);
          border-radius: 999px;
          background: var(--color-control-bg);
          color: var(--color-text-muted);
          cursor: pointer;
          transition: border-color var(--transition-fast), background var(--transition-fast);
        }
        .theme-toggle:hover {
          border-color: var(--color-border-hover);
          background: var(--color-control-hover-bg);
        }
        .theme-toggle__option {
          min-width: 48px;
          padding: 6px 9px;
          border-radius: 999px;
          font-size: 11px;
          font-weight: 800;
          letter-spacing: 0.06em;
          text-transform: uppercase;
          text-align: center;
        }
        .theme-toggle__option--active {
          background: var(--color-control-active-bg);
          color: var(--color-accent-blue);
          box-shadow: inset 0 0 0 1px var(--color-control-active-border);
        }
      `}</style>
    </button>
  );
}
