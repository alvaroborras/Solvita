import { useEffect, useMemo, useState } from 'react';
import { FinalArtifactSnapshot, RunArtifacts, SolutionSnapshot } from '../types/artifacts';
import { JourneyStageId, JourneyTimelineEntry } from '../types/journey';
import { showcaseReferenceSolution } from '../utils/showcaseReferenceSolutions';
import { localizeDashboardText, useI18n } from '../i18n';

interface EvidenceWorkbenchProps {
  stageId: JourneyStageId | null;
  timelineEntry: JourneyTimelineEntry | null;
  problem: Record<string, unknown> | null;
  artifacts: RunArtifacts;
}

type EvidenceTab = 'code' | 'tests' | 'result' | 'counterexample';

interface DiffLine {
  kind: 'same' | 'added' | 'removed' | 'changed';
  left?: string;
  right?: string;
}

function stageDefaultTab(stageId: JourneyStageId | null): EvidenceTab {
  switch (stageId) {
    case 'codegen':
      return 'code';
    case 'full_testgen':
      return 'tests';
    case 'hack':
      return 'counterexample';
    default:
      return 'result';
  }
}

function chooseSolutionSnapshot(
  stageId: JourneyStageId | null,
  timelineEntry: JourneyTimelineEntry | null,
  artifacts: RunArtifacts
): SolutionSnapshot | null {
  const snapshots = artifacts.solutionSnapshots;
  if (snapshots.length === 0) return null;
  if (stageId === 'codegen' && timelineEntry) {
    const matched = snapshots.find((snapshot) => snapshot.version === timelineEntry.visit);
    if (matched) return matched;
  }
  return snapshots[snapshots.length - 1];
}

function artifactOrFallbackCode(snapshot: SolutionSnapshot | null, artifact: FinalArtifactSnapshot | null): string {
  if (snapshot?.code) return snapshot.code;
  return artifact?.solution.code || '';
}

function previousSolutionSnapshot(
  current: SolutionSnapshot | null,
  artifacts: RunArtifacts
): SolutionSnapshot | null {
  if (!current) return null;
  const idx = artifacts.solutionSnapshots.findIndex((snapshot) => snapshot.seq === current.seq);
  if (idx <= 0) return null;
  return artifacts.solutionSnapshots[idx - 1];
}

function computeLineDiff(leftText: string, rightText: string): DiffLine[] {
  const left = leftText.split('\n');
  const right = rightText.split('\n');
  const maxLen = Math.max(left.length, right.length);
  const diff: DiffLine[] = [];
  for (let index = 0; index < maxLen; index += 1) {
    const leftLine = left[index];
    const rightLine = right[index];
    if (leftLine === undefined && rightLine !== undefined) {
      diff.push({ kind: 'added', right: rightLine });
    } else if (leftLine !== undefined && rightLine === undefined) {
      diff.push({ kind: 'removed', left: leftLine });
    } else if (leftLine === rightLine) {
      diff.push({ kind: 'same', left: leftLine, right: rightLine });
    } else {
      diff.push({ kind: 'changed', left: leftLine, right: rightLine });
    }
  }
  return diff;
}

function preview(text: string | undefined, empty = '—'): string {
  const value = (text || '').trim();
  return value || empty;
}

export default function EvidenceWorkbench({
  stageId,
  timelineEntry,
  problem,
  artifacts,
}: EvidenceWorkbenchProps) {
  const { language, t } = useI18n();
  const [tab, setTab] = useState<EvidenceTab>(stageDefaultTab(stageId));

  useEffect(() => {
    setTab(stageDefaultTab(stageId));
  }, [stageId, timelineEntry?.id]);

  const finalArtifact = artifacts.finalArtifact;
  const solutionSnapshot = useMemo(
    () => chooseSolutionSnapshot(stageId, timelineEntry, artifacts),
    [artifacts, stageId, timelineEntry]
  );
  const previousSnapshot = useMemo(
    () => previousSolutionSnapshot(solutionSnapshot, artifacts),
    [artifacts, solutionSnapshot]
  );
  const referenceSolution = useMemo(() => showcaseReferenceSolution(problem), [problem]);
  const emittedCode = artifactOrFallbackCode(solutionSnapshot, finalArtifact);
  const code = emittedCode || referenceSolution?.code || '';
  const codeLabel = emittedCode ? 'emitted solution' : referenceSolution?.label || '';
  const tabLabel = (nextTab: EvidenceTab) => localizeDashboardText(language, nextTab);
  const codeDiff = useMemo(
    () => previousSnapshot && emittedCode && previousSnapshot.code !== emittedCode
      ? computeLineDiff(previousSnapshot.code, code)
      : [],
    [code, emittedCode, previousSnapshot]
  );
  const publicTests = Array.isArray(problem?.public_tests) ? problem.public_tests as Array<Record<string, unknown>> : [];
  const generatedTests = finalArtifact?.tests.generatedTests || [];
  const hackFailures = finalArtifact?.hack.failures || [];

  return (
    <section className="evidence-workbench surface-card">
      <div className="evidence-workbench__head">
        <div>
          <div className="surface-kicker">{t('evidenceWorkbench')}</div>
          <h2 className="surface-title">{t('evidenceWorkbenchTitle')}</h2>
        </div>
        {timelineEntry && <span className="evidence-workbench__tag">{timelineEntry.title}</span>}
      </div>

      <div className="evidence-tabs">
        {(['code', 'tests', 'result', 'counterexample'] as const).map((nextTab) => (
          <button
            key={nextTab}
            type="button"
            className={`evidence-tabs__tab ${tab === nextTab ? 'evidence-tabs__tab--active' : ''}`}
            onClick={() => setTab(nextTab)}
          >
            {tabLabel(nextTab)}
          </button>
        ))}
      </div>

      {tab === 'code' && (
        <div className="evidence-workbench__body">
          {code ? (
            <>
              <div className="evidence-workbench__meta">
                <span>{localizeDashboardText(language, 'version')} {solutionSnapshot?.version ?? finalArtifact?.solution.version ?? 0}</span>
                <span>{(solutionSnapshot?.lineCount ?? finalArtifact?.solution.lineCount ?? code.split('\n').length)} {localizeDashboardText(language, 'lines')}</span>
                {codeLabel && <span>{localizeDashboardText(language, codeLabel)}</span>}
                {previousSnapshot && emittedCode && <span>{localizeDashboardText(language, 'diff vs')} v{previousSnapshot.version}</span>}
              </div>
              <pre className="evidence-workbench__code"><code>{code}</code></pre>
              {codeDiff.length > 0 && (
                <div className="evidence-workbench__diffPanel">
                  <div className="evidence-workbench__panelTitle">{localizeDashboardText(language, 'Code diff')}</div>
                  <div className="evidence-workbench__diffList">
                    {codeDiff.map((line, index) => (
                      <div key={`code-diff-${index}`} className={`evidence-workbench__diffLine evidence-workbench__diffLine--${line.kind}`}>
                        <span className="evidence-workbench__diffMarker">
                          {line.kind === 'added' ? '+' : line.kind === 'removed' ? '-' : line.kind === 'changed' ? '±' : '·'}
                        </span>
                        <span className="evidence-workbench__diffText">
                          {line.kind === 'changed'
                            ? `${localizeDashboardText(language, 'old')}: ${line.left || ''} | ${localizeDashboardText(language, 'new')}: ${line.right || ''}`
                            : line.right || line.left || ''}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : (
            <p className="evidence-workbench__empty">{localizeDashboardText(language, 'No emitted solution snapshot is available yet for this run.')}</p>
          )}
        </div>
      )}

      {tab === 'tests' && (
        <div className="evidence-workbench__body">
          <div className="evidence-workbench__testColumns">
            <div className="evidence-workbench__panel">
              <div className="evidence-workbench__panelTitle">{localizeDashboardText(language, 'Public / trusted tests')}</div>
              {publicTests.length > 0 ? publicTests.map((test, index) => (
                <div key={`public-${index}`} className="evidence-workbench__case">
                  <div className="evidence-workbench__caseLabel">{localizeDashboardText(language, 'sample')} #{index + 1}</div>
                  <pre>{preview(String(test.input || ''))}</pre>
                  <pre>{preview(String(test.output || ''))}</pre>
                </div>
              )) : <p className="evidence-workbench__empty">{localizeDashboardText(language, 'No public tests were provided.')}</p>}
            </div>

            <div className="evidence-workbench__panel">
              <div className="evidence-workbench__panelTitle">{localizeDashboardText(language, 'Generated / carried tests')}</div>
              {generatedTests.length > 0 ? generatedTests.map((test, index) => (
                <div key={`generated-${index}`} className="evidence-workbench__case">
                  <div className="evidence-workbench__caseLabel">
                    {localizeDashboardText(language, (test.type || test.trust_tier || 'generated').toString())}
                  </div>
                  <pre>{preview(test.input || '')}</pre>
                  <pre>{preview(test.expected_output || test.output || '')}</pre>
                </div>
              )) : <p className="evidence-workbench__empty">{localizeDashboardText(language, 'No generated test snapshot is available yet.')}</p>}
            </div>
          </div>
        </div>
      )}

      {tab === 'result' && (
        <div className="evidence-workbench__body">
          <div className="evidence-workbench__resultGrid">
            <div className="evidence-workbench__panel">
              <div className="evidence-workbench__panelTitle">{localizeDashboardText(language, 'Final result')}</div>
              <div className="evidence-workbench__bigValue">
                {localizeDashboardText(language, finalArtifact?.status || 'not reached')}
              </div>
              <div className="evidence-workbench__meta">
                <span>{localizeDashboardText(language, 'visible tests')} {finalArtifact ? `${finalArtifact.tests.passedTests}/${finalArtifact.tests.totalTests}` : '—'}</span>
                <span>{localizeDashboardText(language, 'full testgen')} {localizeDashboardText(language, finalArtifact?.tests.fullTestgenCompleted ? 'done' : 'skipped')}</span>
              </div>
              <p className="evidence-workbench__paragraph">
                {finalArtifact?.feedback.analysis ? localizeDashboardText(language, finalArtifact.feedback.analysis) : localizeDashboardText(language, 'No final feedback summary was emitted.')}
              </p>
            </div>

            <div className="evidence-workbench__panel">
              <div className="evidence-workbench__panelTitle">{localizeDashboardText(language, 'Risk flags / log tail')}</div>
              <div className="evidence-workbench__chips">
                {Object.keys(finalArtifact?.tests.trustTiers || {}).map((flag) => (
                  <span key={flag} className="evidence-workbench__chip">{localizeDashboardText(language, flag)}</span>
                ))}
              </div>
              {(finalArtifact?.executionLogTail || []).slice(-5).map((line, index) => (
                <div key={`log-${index}`} className="evidence-workbench__logLine">{localizeDashboardText(language, line)}</div>
              ))}
            </div>
          </div>
        </div>
      )}

      {tab === 'counterexample' && (
        <div className="evidence-workbench__body">
          <div className="evidence-workbench__testColumns">
            <div className="evidence-workbench__panel">
              <div className="evidence-workbench__panelTitle">{localizeDashboardText(language, 'Hack counterexamples')}</div>
              {hackFailures.length > 0 ? hackFailures.map((failure, index) => (
                <div key={`hack-${index}`} className="evidence-workbench__case">
                  <div className="evidence-workbench__caseLabel">{localizeDashboardText(language, failure.failure_type || 'hack failure')}</div>
                  <pre>{preview(failure.input || failure.input_text)}</pre>
                  <div className="evidence-workbench__caseSplit">
                    <div>
                      <div className="evidence-workbench__caseSubLabel">{localizeDashboardText(language, 'expected')}</div>
                      <pre>{preview(failure.expected || failure.expected_output)}</pre>
                    </div>
                    <div>
                      <div className="evidence-workbench__caseSubLabel">{localizeDashboardText(language, 'actual')}</div>
                      <pre>{preview(failure.output || failure.actual_output)}</pre>
                    </div>
                  </div>
                  <div className="evidence-workbench__diffList">
                    {computeLineDiff(
                      preview(failure.expected || failure.expected_output, ''),
                      preview(failure.output || failure.actual_output, '')
                    ).map((line, diffIndex) => (
                      <div key={`hack-diff-${index}-${diffIndex}`} className={`evidence-workbench__diffLine evidence-workbench__diffLine--${line.kind}`}>
                        <span className="evidence-workbench__diffMarker">
                          {line.kind === 'added' ? '+' : line.kind === 'removed' ? '-' : line.kind === 'changed' ? '±' : '·'}
                        </span>
                        <span className="evidence-workbench__diffText">
                          {line.kind === 'changed'
                            ? `${localizeDashboardText(language, 'expected')}: ${line.left || ''} | ${localizeDashboardText(language, 'actual')}: ${line.right || ''}`
                            : line.right || line.left || ''}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )) : <p className="evidence-workbench__empty">{localizeDashboardText(language, 'No adversarial break case is stored for this run.')}</p>}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
