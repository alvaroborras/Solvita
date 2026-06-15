import { FinalArtifactSnapshot } from '../types/artifacts';
import { JourneyTimelineEntry } from '../types/journey';
import { DashboardLanguage, localizeDashboardText, useI18n } from '../i18n';

interface FinalSummaryCardProps {
  problemName: string;
  finalStatus: string | null;
  timeline: JourneyTimelineEntry[];
  artifact: FinalArtifactSnapshot | null;
}

function describeOutcome(finalStatus: string | null, artifact: FinalArtifactSnapshot | null, language: DashboardLanguage): string {
  if (finalStatus === 'success') {
    if (artifact?.hack.result === 'SAFE') {
      if (language === 'zh') return '求解器通过了可见检查，并经受住了对抗 Hack 轮次。';
      return 'The solver passed the visible checks and survived adversarial hack rounds.';
    }
    if (language === 'zh') return '工作流达成可接受解并干净停止。';
    return 'The workflow reached an accepted solution and stopped cleanly.';
  }
  if (finalStatus === 'cancelled') {
    if (language === 'zh') return '用户在求解器得到最终接受答案前中断了本次运行。';
    return 'The run was interrupted by the user before the solver reached a final accepted answer.';
  }
  if (finalStatus === 'max_iterations') {
    if (language === 'zh') return '求解器耗尽修复预算，仍未产出可信答案。';
    return 'The solver exhausted its repair budget before it could produce a trustworthy answer.';
  }
  if (finalStatus === 'terminal_failure') {
    if (language === 'zh') return '后期反例击破了候选解，工作流以失败停止。';
    return 'A late-stage counterexample broke the candidate and the workflow stopped in failure.';
  }
  if (language === 'zh') return '运行已结束。请检查下方回顾中的决定性步骤。';
  return 'The run has finished. Inspect the recap below for the decisive steps.';
}

function turningPoints(timeline: JourneyTimelineEntry[]): JourneyTimelineEntry[] {
  const interesting = timeline.filter((entry) =>
    entry.status === 'repairing'
    || entry.status === 'failed'
    || entry.stageId === 'hack'
  );
  return interesting.slice(-3);
}

export default function FinalSummaryCard({
  problemName,
  finalStatus,
  timeline,
  artifact,
}: FinalSummaryCardProps) {
  const { language, t } = useI18n();
  if (!finalStatus) return null;

  const visibleTestLabel = artifact
    ? `${artifact.tests.passedTests}/${artifact.tests.totalTests}`
    : '—';
  const hackLabel = localizeDashboardText(language, artifact?.hack.result || 'not used');
  const finalStatusLabel = finalStatus ? localizeDashboardText(language, finalStatus) : '';
  const recap = turningPoints(timeline);

  return (
    <section className="final-summary surface-card">
      <div className="final-summary__head">
        <div>
          <div className="surface-kicker">{t('finalSummary')}</div>
          <h2 className="surface-title">{problemName || t('completedRun')}</h2>
        </div>
        <span className="journey-pill journey-pill--status">{finalStatusLabel}</span>
      </div>

      <p className="final-summary__lede">{describeOutcome(finalStatus, artifact, language)}</p>

      <div className="final-summary__stats">
        <div className="final-summary__stat">
          <span className="final-summary__label">{t('iteration')}</span>
          <span className="final-summary__value">{artifact?.iteration ?? 0}</span>
        </div>
        <div className="final-summary__stat">
          <span className="final-summary__label">{t('visibleTests')}</span>
          <span className="final-summary__value">{visibleTestLabel}</span>
        </div>
        <div className="final-summary__stat">
          <span className="final-summary__label">{t('hackResult')}</span>
          <span className="final-summary__value final-summary__value--small">{hackLabel}</span>
        </div>
      </div>

      {recap.length > 0 && (
        <div className="final-summary__recap">
          <div className="surface-kicker">{t('turningPoints')}</div>
          <div className="final-summary__recapList">
            {recap.map((entry) => (
              <div key={entry.id} className="final-summary__recapItem">
                <div className="final-summary__recapTitle">{entry.title}</div>
                <div className="final-summary__recapText">{entry.summary}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
