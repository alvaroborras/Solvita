import type { FailureAnalysis } from '../utils/failureAnalysis';
import { localizeDashboardText, useI18n } from '../i18n';

interface FailureAnalysisCardProps {
  analysis: FailureAnalysis | null;
}

function sectionVisible(lines: string[]): boolean {
  return lines.some((line) => line.trim().length > 0);
}

export default function FailureAnalysisCard({ analysis }: FailureAnalysisCardProps) {
  const { language } = useI18n();

  if (!analysis) {
    return null;
  }

  const localize = (text: string) => localizeDashboardText(language, text);

  const {
    headline,
    summary,
    rootCause,
    chain,
    signals,
  } = analysis;

  return (
    <section className="failure-analysis surface-card">
      <div className="failure-analysis__head">
        <div>
          <div className="surface-kicker">{localize('Failure Analysis')}</div>
          <h2 className="surface-title">{localize(headline)}</h2>
        </div>
        <span className="journey-pill journey-pill--status journey-pill--failed">{localize('needs repair')}</span>
      </div>

      <p className="failure-analysis__lede">{localize(summary)}</p>

      <div className="failure-analysis__root">
        <div className="failure-analysis__sectionLabel">{localize('Likely root cause')}</div>
        <div className="failure-analysis__rootText">{localize(rootCause)}</div>
      </div>

      <div className="failure-analysis__body">
        <div className="failure-analysis__panel">
          <div className="failure-analysis__sectionLabel">{localize('Failure chain')}</div>
          <div className="failure-analysis__chain">
            {chain.map((item) => (
              <div key={item.id} className={`failure-analysis__chainItem failure-analysis__chainItem--${item.status}`}>
                <div className="failure-analysis__chainMeta">
                  <span className="failure-analysis__chainStage">{localize(item.stageLabel)}</span>
                  <span className="failure-analysis__chainTitle">{localize(item.title)}</span>
                </div>
                <div className="failure-analysis__chainSummary">{localize(item.summary)}</div>
                {item.evidence.length > 0 && (
                  <div className="failure-analysis__chips">
                    {item.evidence.map((line, index) => (
                      <span key={`${item.id}-evidence-${index}`} className="failure-analysis__chip">
                        {localize(line)}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        <div className="failure-analysis__panel">
          <div className="failure-analysis__sectionLabel">{localize('Structured signals')}</div>
          <div className="failure-analysis__signalGrid">
            {sectionVisible(signals.compilationErrors) && (
              <div className="failure-analysis__signalBlock">
                <div className="failure-analysis__signalTitle">{localize('Compilation errors')}</div>
                {signals.compilationErrors.map((line, index) => (
                  <div key={`compile-${index}`} className="failure-analysis__signalLine">{localize(line)}</div>
                ))}
              </div>
            )}

            {sectionVisible(signals.suggestedFixes) && (
              <div className="failure-analysis__signalBlock">
                <div className="failure-analysis__signalTitle">{localize('Suggested fixes')}</div>
                {signals.suggestedFixes.map((line, index) => (
                  <div key={`fix-${index}`} className="failure-analysis__signalLine">{localize(line)}</div>
                ))}
              </div>
            )}

            {sectionVisible(signals.hackFailures) && (
              <div className="failure-analysis__signalBlock">
                <div className="failure-analysis__signalTitle">{localize('Hack failures')}</div>
                {signals.hackFailures.map((line, index) => (
                  <div key={`hack-${index}`} className="failure-analysis__signalLine">{localize(line)}</div>
                ))}
              </div>
            )}

            {sectionVisible(signals.errorEvents) && (
              <div className="failure-analysis__signalBlock">
                <div className="failure-analysis__signalTitle">{localize('Runtime errors')}</div>
                {signals.errorEvents.map((line, index) => (
                  <div key={`runtime-${index}`} className="failure-analysis__signalLine">{localize(line)}</div>
                ))}
              </div>
            )}

            {sectionVisible(signals.executionLogTail) && (
              <div className="failure-analysis__signalBlock">
                <div className="failure-analysis__signalTitle">{localize('Execution log tail')}</div>
                {signals.executionLogTail.map((line, index) => (
                  <div key={`log-${index}`} className="failure-analysis__signalLine failure-analysis__signalLine--mono">
                    {localize(line)}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
