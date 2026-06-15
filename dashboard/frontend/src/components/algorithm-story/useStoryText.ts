import { localizeDashboardText, useI18n } from '../../i18n';

export function useStoryText() {
  const { language } = useI18n();
  return (text: string) => localizeDashboardText(language, text);
}
