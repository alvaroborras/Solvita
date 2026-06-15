import { parseProblemStatement } from '../utils/problemStatement';
import { useI18n } from '../i18n';

interface ProblemStatementCardProps {
  problem: Record<string, unknown> | null;
  mode?: 'full' | 'compact';
}

const readableTextStyle = {
  overflow: 'visible',
  textOverflow: 'clip',
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
} as const;

function asReadableLabel(value: unknown): string | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return String(value);
  }
  if (typeof value === 'string' && value.trim()) {
    return value.trim();
  }
  return null;
}

function buildChips(meta: Record<string, unknown> & { timeLimit: number | null; spaceLimit: number | null }) {
  const chips = [
    asReadableLabel(meta.source),
    asReadableLabel(meta.family),
    asReadableLabel(meta.difficulty),
    meta.timeLimit !== null ? `${meta.timeLimit} ms` : null,
    meta.spaceLimit !== null ? `${meta.spaceLimit} MB` : null,
  ];

  return chips.filter((chip): chip is string => Boolean(chip));
}

function StatementSection({
  title,
  content,
  code = false,
  testId,
}: {
  title: string;
  content: string;
  code?: boolean;
  testId?: string;
}) {
  if (!content) return null;

  return (
    <section className="statement-card__section">
      <h3 className="statement-card__sectionTitle">{title}</h3>
      <pre
        className={code ? 'statement-card__code' : 'statement-card__bodyText'}
        data-testid={testId}
        style={readableTextStyle}
      >
        {content}
      </pre>
    </section>
  );
}

export default function ProblemStatementCard({
  problem,
  mode = 'full',
}: ProblemStatementCardProps) {
  const { t } = useI18n();
  if (!problem) return null;

  const statement = parseProblemStatement(problem);
  const chips = buildChips(statement.meta);
  const kicker = mode === 'compact' ? t('problemPreview') : t('problemStatement');
  const className = mode === 'compact'
    ? 'statement-card statement-card--compact'
    : 'statement-card';

  return (
    <section className={className}>
      <header className="statement-card__header">
        <div className="surface-kicker">{kicker}</div>
        {statement.title && <h2 className="surface-title">{statement.title}</h2>}
        {chips.length > 0 && (
          <div className="statement-card__chips">
            {chips.map((chip) => (
              <span key={chip} className="statement-card__chip">
                {chip}
              </span>
            ))}
          </div>
        )}
      </header>

      {statement.bodySections.map((section, index) => (
        <section key={`${section.heading}-${index}`} className="statement-card__section">
          {section.heading && <h3 className="statement-card__sectionTitle">{section.heading}</h3>}
          <pre
            className="statement-card__bodyText"
            data-testid={`statement-card-body-${index}`}
            style={readableTextStyle}
          >
            {section.content}
          </pre>
        </section>
      ))}

      <StatementSection
        title={t('inputFormat')}
        content={statement.inputFormat}
        code
        testId="statement-card-input-format"
      />
      <StatementSection
        title={t('outputFormat')}
        content={statement.outputFormat}
        code
        testId="statement-card-output-format"
      />
      <StatementSection
        title={t('constraints')}
        content={statement.constraints}
        code
        testId="statement-card-constraints"
      />
      <StatementSection title={t('complexity')} content={statement.complexity} testId="statement-card-complexity" />
      <StatementSection title={t('explanation')} content={statement.explanation} testId="statement-card-explanation" />

      {statement.samples.length > 0 && (
        <section className="statement-card__section">
          <h3 className="statement-card__sectionTitle">{t('samples')}</h3>
          <div className="statement-card__samples">
            {statement.samples.map((sample) => (
              <article key={sample.title} className="statement-card__sample">
                <h4 className="statement-card__sampleTitle">{sample.title}</h4>
                <div className="statement-card__sampleLabel">{t('input')}</div>
                <pre className="statement-card__code" style={readableTextStyle}>
                  {sample.input}
                </pre>
                <div className="statement-card__sampleLabel">{t('output')}</div>
                <pre className="statement-card__code" style={readableTextStyle}>
                  {sample.output}
                </pre>
              </article>
            ))}
          </div>
        </section>
      )}
    </section>
  );
}
