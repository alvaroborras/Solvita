import { useI18n } from '../i18n';

export default function LanguageToggle() {
  const { language, t, toggleLanguage } = useI18n();
  const nextLabel = language === 'en' ? t('languageToggleToZh') : t('languageToggleToEn');

  return (
    <button
      type="button"
      className="language-toggle"
      aria-label={nextLabel}
      onClick={toggleLanguage}
    >
      <span className={language === 'en' ? 'language-toggle__option language-toggle__option--active' : 'language-toggle__option'}>
        {t('languageEnglishShort')}
      </span>
      <span className={language === 'zh' ? 'language-toggle__option language-toggle__option--active' : 'language-toggle__option'}>
        {t('languageChineseShort')}
      </span>

      <style>{`
        .language-toggle {
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
        .language-toggle:hover {
          border-color: var(--color-border-hover);
          background: var(--color-control-hover-bg);
        }
        .language-toggle__option {
          min-width: 34px;
          padding: 6px 9px;
          border-radius: 999px;
          font-size: 11px;
          font-weight: 800;
          letter-spacing: 0.06em;
          text-transform: uppercase;
          text-align: center;
        }
        .language-toggle__option--active {
          background: var(--color-control-active-bg);
          color: var(--color-accent-blue);
          box-shadow: inset 0 0 0 1px var(--color-control-active-border);
        }
      `}</style>
    </button>
  );
}
