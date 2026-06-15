import type { AbstractInsight } from '../utils/abstractInsight';
import { DashboardLanguage, useI18n } from '../i18n';

interface RunContextCardProps {
  mode: 'live' | 'replay' | 'idle';
  runId: string | null;
  problemName: string;
  problem: Record<string, unknown> | null;
  config: Record<string, unknown> | null;
  abstractInsight?: AbstractInsight | null;
  eventCount: number;
  stageCount: number;
  touchedStageCount: number;
  completedStageCount: number;
  currentStageLabel: string;
  replayCursor?: number;
  replayTotal?: number;
  finalStatus?: string | null;
}

function text(value: unknown): string {
  if (value === null || value === undefined) return '';
  return String(value);
}

function difficultyLabel(value: unknown): string {
  if (typeof value === 'number') return `difficulty ${value}`;
  const raw = text(value).trim();
  return raw ? raw : 'unrated';
}

function buildRunNarrative({
  language,
  mode,
  currentStageLabel,
  finalStatus,
  replayCursor,
  replayTotal,
  eventCount,
}: {
  language: DashboardLanguage;
  mode: RunContextCardProps['mode'];
  currentStageLabel: string;
  finalStatus: string | null;
  replayCursor: number;
  replayTotal: number;
  eventCount: number;
}): string {
  const stageLabel = currentStageLabel || (language === 'zh' ? '下一阶段' : 'the next stage');

  if (finalStatus) {
    if (language === 'zh') {
      return `最终总结：本次运行以 ${finalStatus} 结束，结束时聚焦在 ${stageLabel}。可使用下方时间线和产物复盘记录结果。`;
    }
    return `Final summary: this run ended with ${finalStatus} while focused on ${stageLabel}. Use the timeline and artifacts below to review the recorded outcome.`;
  }

  if (mode === 'replay') {
    const totalEvents = replayTotal || eventCount;
    if (language === 'zh') {
      return `回放当前聚焦在 ${stageLabel}。逐步查看 ${replayCursor}/${totalEvents} 个记录事件，检查运行如何展开。`;
    }
    return `Replay is focused on ${stageLabel}. Step through ${replayCursor}/${totalEvents} recorded events to inspect how the run unfolded.`;
  }

  if (mode === 'live') {
    if (language === 'zh') {
      return `实时运行当前位于 ${stageLabel}。AlgoPilot 仍在推进当前尝试，所以这张卡聚焦运行进度，而不是重复完整题面。`;
    }
    return `Live run is currently in ${stageLabel}. AlgoPilot is still working through the active attempt, so this card stays focused on run progress instead of repeating the full prompt.`;
  }

  if (language === 'zh') {
    return '当前没有活跃运行。开始求解后，这里会展示运行身份、阶段进度和回放摘要。';
  }
  return 'No run is active yet. Start a solve to populate the run identity, stage progress, and playback summary here.';
}

function buildMetaChips(problem: Record<string, unknown> | null, config: Record<string, unknown> | null): string[] {
  const metadata = ((problem?._metadata as Record<string, unknown> | undefined) || {});
  const chips: string[] = [];
  const pushChip = (chip: string) => {
    if (!chip || chips.includes(chip)) {
      return;
    }
    chips.push(chip);
  };
  const source = text(metadata.source || metadata.benchmark_source);
  const family = text(metadata.family);
  const showcase = Boolean(metadata.showcase ?? metadata.is_showcase ?? problem?.is_showcase);
  const platform = text(metadata.platform);
  const difficulty = difficultyLabel(metadata.difficulty);
  const questionId = text(metadata.question_id || metadata.problem_id);
  const maxIterations = config && typeof config.max_iterations === 'number'
    ? `max ${config.max_iterations} iters`
    : '';

  if (source) pushChip(source);
  if (family) pushChip(family);
  if (showcase) pushChip('showcase');
  if (platform) pushChip(platform);
  if (difficulty && difficulty !== 'unrated') pushChip(difficulty);
  if (questionId) pushChip(questionId);
  if (maxIterations) pushChip(maxIterations);
  if (chips.length === 0) pushChip('custom input');
  return chips;
}

function formatConfidence(value: number | null): string | null {
  if (value === null) return null;
  return `${Math.round(value * 100)}% confidence`;
}

export default function RunContextCard({
  mode,
  runId,
  problemName,
  problem,
  config,
  abstractInsight = null,
  eventCount,
  stageCount,
  touchedStageCount,
  completedStageCount,
  currentStageLabel,
  replayCursor = 0,
  replayTotal = 0,
  finalStatus = null,
}: RunContextCardProps) {
  const { language, t } = useI18n();
  const publicTests = Array.isArray(problem?.public_tests) ? problem.public_tests.length : 0;
  const stageProgress = stageCount > 0 ? (touchedStageCount / stageCount) * 100 : 0;
  const completedProgress = stageCount > 0 ? (completedStageCount / stageCount) * 100 : 0;
  const playbackLabel = mode === 'replay'
    ? `${replayCursor}/${replayTotal || 0} ${t('replayEvents')}`
    : `${eventCount} ${t('canonicalEvents')}`;
  const chips = buildMetaChips(problem, config);
  const abstractConfidence = abstractInsight ? formatConfidence(abstractInsight.confidence) : null;
  const narrative = buildRunNarrative({
    language,
    mode,
    currentStageLabel,
    finalStatus,
    replayCursor,
    replayTotal,
    eventCount,
  });

  return (
    <section className="run-context surface-card">
      <div className="run-context__head">
        <div>
          <div className="surface-kicker">{t('runContext')}</div>
          <h2 className="surface-title">{problemName || t('noActiveRun')}</h2>
        </div>
        <div className="run-context__statusStack">
          {runId && <span className="run-context__id">run {runId.slice(0, 8)}</span>}
          <span className={`journey-pill journey-pill--mode journey-pill--mode-${mode}`}>{mode}</span>
          {finalStatus && <span className="journey-pill journey-pill--status">{finalStatus}</span>}
        </div>
      </div>

      <div className="run-context__chips">
        {chips.map((chip) => (
          <span key={chip} className="run-context__chip">{chip}</span>
        ))}
      </div>

      {abstractInsight && abstractInsight.tags.length > 0 && (
        <div className="run-context__abstractTags" aria-label="Abstract phase interpreted tags">
          <span className="run-context__abstractLabel">{t('abstractTags')}</span>
          <div className="run-context__abstractChipGroup">
            {abstractInsight.tags.map((tag) => (
              <span key={tag} className="run-context__chip run-context__chip--abstract">{tag}</span>
            ))}
            {abstractConfidence && (
              <span className="run-context__chip run-context__chip--confidence">{abstractConfidence}</span>
            )}
          </div>
        </div>
      )}

      <div className="run-context__grid">
        <div className="run-context__narrative">
          <p className="run-context__description">{narrative}</p>
          <div className="run-context__facts">
            <div className="run-context__fact">
              <span className="run-context__factLabel">{t('currentStage')}</span>
              <span className="run-context__factValue">{currentStageLabel || t('waiting')}</span>
            </div>
            <div className="run-context__fact">
              <span className="run-context__factLabel">{t('publicSamples')}</span>
              <span className="run-context__factValue">{publicTests}</span>
            </div>
            <div className="run-context__fact">
              <span className="run-context__factLabel">{t('playback')}</span>
              <span className="run-context__factValue">{playbackLabel}</span>
            </div>
          </div>
        </div>

        <div className="run-context__progressCard">
          <div className="run-context__progressHead">
            <span className="surface-kicker">{t('algoPilotJourney')}</span>
            <span className="run-context__progressValue">{completedStageCount}/{stageCount}</span>
          </div>
          <div className="run-context__bar">
            <div className="run-context__barResolved" style={{ width: `${stageProgress}%` }} />
            <div className="run-context__barCompleted" style={{ width: `${completedProgress}%` }} />
          </div>
          <div className="run-context__progressLegend">
            <span>{touchedStageCount} {t('touched')}</span>
            <span>{completedStageCount} {t('finished')}</span>
            <span>{stageCount - touchedStageCount} {t('ahead')}</span>
          </div>
        </div>
      </div>
    </section>
  );
}
