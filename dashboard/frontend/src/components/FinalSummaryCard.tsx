import { FinalArtifactSnapshot } from '../types/artifacts';
import { JourneyTimelineEntry } from '../types/journey';

interface FinalSummaryCardProps {
  problemName: string;
  finalStatus: string | null;
  timeline: JourneyTimelineEntry[];
  artifact: FinalArtifactSnapshot | null;
}

function describeOutcome(finalStatus: string | null, artifact: FinalArtifactSnapshot | null): string {
  if (finalStatus === 'success') {
    if (artifact?.hack.result === 'SAFE') {
      return 'The solver passed verification and also survived adversarial hack checks.';
    }
    return 'The workflow reached an accepted solution and stopped cleanly.';
  }
  if (finalStatus === 'cancelled') {
    return 'The run was interrupted by the user before the solver reached a final accepted answer.';
  }
  if (finalStatus === 'max_iterations') {
    return 'The solver exhausted its repair budget before it could produce a trustworthy answer.';
  }
  if (finalStatus === 'terminal_failure') {
    return 'A late-stage counterexample broke the candidate and the workflow stopped in failure.';
  }
  return 'The run has finished. Inspect the recap below for the decisive steps.';
}

function turningPoints(timeline: JourneyTimelineEntry[]): JourneyTimelineEntry[] {
  const interesting = timeline.filter((entry) =>
    entry.status === 'repairing'
    || entry.status === 'failed'
    || entry.stageId === 'verify'
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
  if (!finalStatus) return null;

  const visibleTestLabel = artifact
    ? `${artifact.tests.passedTests}/${artifact.tests.totalTests}`
    : '—';
  const verifierLabel = artifact?.verification.decision
    ? artifact.verification.decision.replace(/_/g, ' ')
    : '—';
  const hackLabel = artifact?.hack.result || 'not used';
  const recap = turningPoints(timeline);

  return (
    <section className="final-summary surface-card">
      <div className="final-summary__head">
        <div>
          <div className="surface-kicker">Final Summary</div>
          <h2 className="surface-title">{problemName || 'Completed Run'}</h2>
        </div>
        <span className="journey-pill journey-pill--status">{finalStatus}</span>
      </div>

      <p className="final-summary__lede">{describeOutcome(finalStatus, artifact)}</p>

      <div className="final-summary__stats">
        <div className="final-summary__stat">
          <span className="final-summary__label">Iterations</span>
          <span className="final-summary__value">{artifact?.iteration ?? 0}</span>
        </div>
        <div className="final-summary__stat">
          <span className="final-summary__label">Visible Tests</span>
          <span className="final-summary__value">{visibleTestLabel}</span>
        </div>
        <div className="final-summary__stat">
          <span className="final-summary__label">Verifier</span>
          <span className="final-summary__value final-summary__value--small">{verifierLabel}</span>
        </div>
        <div className="final-summary__stat">
          <span className="final-summary__label">Hack Result</span>
          <span className="final-summary__value final-summary__value--small">{hackLabel}</span>
        </div>
      </div>

      {recap.length > 0 && (
        <div className="final-summary__recap">
          <div className="surface-kicker">Turning Points</div>
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
