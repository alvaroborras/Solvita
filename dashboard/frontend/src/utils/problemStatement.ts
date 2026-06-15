type RawProblem = {
  description?: unknown;
  public_tests?: unknown;
  time_limit?: unknown;
  space_limit?: unknown;
  _metadata?: unknown;
};

type StatementSectionType =
  | 'problem'
  | 'input'
  | 'output'
  | 'sample'
  | 'sample_input'
  | 'sample_output'
  | 'explanation'
  | 'constraints'
  | 'complexity'
  | 'unknown';

type ParsedSection = {
  heading: string;
  type: StatementSectionType;
  content: string;
};

export type ProblemStatementSection = {
  heading: string;
  content: string;
};

export type ProblemStatementSample = {
  title: string;
  input: string;
  output: string;
};

export type ProblemStatementViewModel = {
  title: string;
  bodySections: ProblemStatementSection[];
  inputFormat: string;
  outputFormat: string;
  constraints: string;
  complexity: string;
  explanation: string;
  samples: ProblemStatementSample[];
  meta: Record<string, unknown> & {
    timeLimit: number | null;
    spaceLimit: number | null;
    usedFallback: boolean;
  };
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asOptionalNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function normalizeNewlines(value: string): string {
  return value.replace(/\r\n?/g, '\n');
}

function trimSectionContent(value: string): string {
  return value.replace(/^\n+|\n+$/g, '');
}

function classifyHeading(line: string): { heading: string; type: StatementSectionType } | null {
  const heading = line.trim().replace(/^#+\s*/, '').replace(/[：:]\s*$/, '');
  if (!heading) return null;

  const compact = heading.replace(/\s+/g, '').toLowerCase();
  const normalized = heading.toLowerCase().replace(/\s+/g, ' ').trim();

  if (compact === '题目描述') return { heading, type: 'problem' };
  if (compact === '输入格式' || compact === '输入') return { heading, type: 'input' };
  if (compact === '输出格式' || compact === '输出') return { heading, type: 'output' };
  if (/^样例\d*$/.test(compact)) return { heading, type: 'sample' };
  if (/^样例\d*输入$/.test(compact)) return { heading, type: 'sample_input' };
  if (/^样例\d*输出$/.test(compact)) return { heading, type: 'sample_output' };
  if (compact === '说明') return { heading, type: 'explanation' };
  if (compact === '约束') return { heading, type: 'constraints' };
  if (compact === '复杂度') return { heading, type: 'complexity' };

  if (normalized === 'problem') return { heading, type: 'problem' };
  if (normalized === 'input' || normalized === 'input format') return { heading, type: 'input' };
  if (normalized === 'output' || normalized === 'output format') return { heading, type: 'output' };
  if (/^(sample|example)s?(?: \d+)?$/.test(normalized)) return { heading, type: 'sample' };
  if (
    /^(sample|example)(?: \d+)? input$/.test(normalized)
    || /^(sample|example) input(?: \d+)?$/.test(normalized)
  ) {
    return { heading, type: 'sample_input' };
  }
  if (
    /^(sample|example)(?: \d+)? output$/.test(normalized)
    || /^(sample|example) output(?: \d+)?$/.test(normalized)
  ) {
    return { heading, type: 'sample_output' };
  }
  if (normalized === 'explanation') return { heading, type: 'explanation' };
  if (normalized === 'constraints') return { heading, type: 'constraints' };
  if (normalized === 'complexity') return { heading, type: 'complexity' };

  return null;
}

function parseSections(description: string): { sections: ParsedSection[]; hasStructure: boolean } {
  const lines = normalizeNewlines(description).split('\n');
  const sections: ParsedSection[] = [];
  let current: ParsedSection | null = null;
  let hasStructure = false;

  const flush = () => {
    if (!current) return;
    const content = trimSectionContent(current.content);
    if (content || current.heading) {
      sections.push({
        heading: current.heading,
        type: current.type,
        content,
      });
    }
    current = null;
  };

  for (const line of lines) {
    const detected = classifyHeading(line);
    if (detected) {
      if (
        current?.type === 'sample'
        && (detected.type === 'input' || detected.type === 'output')
      ) {
        current.content = current.content ? `${current.content}\n${line}` : line;
        continue;
      }

      hasStructure = true;
      flush();
      current = {
        heading: detected.heading,
        type: detected.type,
        content: '',
      };
      continue;
    }

    if (!current) {
      current = {
        heading: '',
        type: 'unknown',
        content: '',
      };
    }

    current.content = current.content ? `${current.content}\n${line}` : line;
  }

  flush();
  return { sections, hasStructure };
}

function appendText(existing: string, next: string): string {
  if (!next) return existing;
  return existing ? `${existing}\n\n${next}` : next;
}

function buildFallbackSamples(publicTests: unknown): ProblemStatementSample[] {
  if (!Array.isArray(publicTests)) return [];

  return publicTests.map((test, index) => {
    const record = asRecord(test);
    return {
      title: `Sample ${index + 1}`,
      input: typeof record.input === 'string' ? record.input : '',
      output: typeof record.output === 'string' ? record.output : '',
    };
  });
}

function getSampleHeadingInfo(heading: string): { titlePrefix: 'Sample' | '样例'; sampleNumber: number | null } {
  const titlePrefix = /样例/.test(heading) ? '样例' : 'Sample';
  const compact = heading.replace(/\s+/g, '');
  const normalized = heading.toLowerCase().replace(/\s+/g, ' ').trim();

  const chineseMatch = compact.match(/^样例(\d+)(?:输入|输出)?$/);
  if (chineseMatch) {
    return {
      titlePrefix,
      sampleNumber: Number.parseInt(chineseMatch[1], 10),
    };
  }

  const englishMatch = normalized.match(
    /^(?:sample|example)(?: (\d+) (?:input|output)| (?:input|output) (\d+))$/,
  );
  if (englishMatch) {
    return {
      titlePrefix,
      sampleNumber: Number.parseInt(englishMatch[1] ?? englishMatch[2], 10),
    };
  }

  return { titlePrefix, sampleNumber: null };
}

function buildSamples(sections: ParsedSection[]): {
  samples: ProblemStatementSample[];
  readableSections: ProblemStatementSection[];
} {
  const samples: ProblemStatementSample[] = [];
  const readableSections: ProblemStatementSection[] = [];
  const numberedSampleIndexes = new Map<string, number>();

  const getOrCreateNumberedSample = (titlePrefix: 'Sample' | '样例', sampleNumber: number) => {
    const key = `${titlePrefix}:${sampleNumber}`;
    const existingIndex = numberedSampleIndexes.get(key);
    if (existingIndex !== undefined) {
      return samples[existingIndex];
    }

    const nextSample: ProblemStatementSample = {
      title: `${titlePrefix} ${sampleNumber}`,
      input: '',
      output: '',
    };
    numberedSampleIndexes.set(key, samples.length);
    samples.push(nextSample);
    return nextSample;
  };

  for (const section of sections) {
    if (section.type === 'sample_input') {
      const { titlePrefix, sampleNumber } = getSampleHeadingInfo(section.heading);
      if (sampleNumber !== null) {
        const sample = getOrCreateNumberedSample(titlePrefix, sampleNumber);
        sample.input = section.content;
      } else {
        samples.push({
          title: `${titlePrefix} ${samples.length + 1}`,
          input: section.content,
          output: '',
        });
      }
      continue;
    }

    if (section.type === 'sample_output') {
      const { titlePrefix, sampleNumber } = getSampleHeadingInfo(section.heading);
      if (sampleNumber !== null) {
        const sample = getOrCreateNumberedSample(titlePrefix, sampleNumber);
        sample.output = section.content;
      } else {
        const current = samples[samples.length - 1];
        if (current && !current.output) {
          current.output = section.content;
        } else {
          samples.push({
            title: `${titlePrefix} ${samples.length + 1}`,
            input: '',
            output: section.content,
          });
        }
      }
      continue;
    }

    if (section.type !== 'sample') continue;

    const lines = section.content.split('\n');
    let mode: 'input' | 'output' | null = null;
    const readableLines: string[] = [];
    let currentSample: { inputLines: string[]; outputLines: string[] } | null = null;
    const titlePrefix = /样例/.test(section.heading) ? '样例' : 'Sample';

    const flushCurrentSample = () => {
      if (!currentSample) return;
      if (currentSample.inputLines.length === 0 && currentSample.outputLines.length === 0) {
        currentSample = null;
        return;
      }

      samples.push({
        title: `${titlePrefix} ${samples.length + 1}`,
        input: trimSectionContent(currentSample.inputLines.join('\n')),
        output: trimSectionContent(currentSample.outputLines.join('\n')),
      });
      currentSample = null;
    };

    for (const line of lines) {
      const trimmed = line.trim();
      const inputMatch = trimmed.match(/^(input|输入)\s*[：:]\s*(.*)$/i);
      const outputMatch = trimmed.match(/^(output|输出)\s*[：:]\s*(.*)$/i);

      if (/^(input|输入)\s*[：:]?\s*$/i.test(trimmed) || inputMatch) {
        if (currentSample && (currentSample.inputLines.length > 0 || currentSample.outputLines.length > 0)) {
          flushCurrentSample();
        }
        currentSample = { inputLines: [], outputLines: [] };
        mode = 'input';
        if (inputMatch && inputMatch[2]) {
          currentSample.inputLines.push(inputMatch[2]);
        }
        continue;
      }
      if (/^(output|输出)\s*[：:]?\s*$/i.test(trimmed) || outputMatch) {
        currentSample ||= { inputLines: [], outputLines: [] };
        mode = 'output';
        if (outputMatch && outputMatch[2]) {
          currentSample.outputLines.push(outputMatch[2]);
        }
        continue;
      }
      if (mode === 'input') {
        currentSample ||= { inputLines: [], outputLines: [] };
        currentSample.inputLines.push(line);
        continue;
      }
      if (mode === 'output') {
        currentSample ||= { inputLines: [], outputLines: [] };
        currentSample.outputLines.push(line);
        } else {
        readableLines.push(line);
      }
      continue;
    }

    flushCurrentSample();

    if (samples.length > 0) {
      const readableContent = trimSectionContent(readableLines.join('\n'));
      if (readableContent) {
        readableSections.push({
          heading: section.heading,
          content: readableContent,
        });
      }
    } else {
      readableSections.push({
        heading: section.heading,
        content: section.content,
      });
    }
  }

  return { samples, readableSections };
}

export function parseProblemStatement(problem: RawProblem): ProblemStatementViewModel {
  const description = typeof problem.description === 'string' ? normalizeNewlines(problem.description) : '';
  const metadata = asRecord(problem._metadata);
  const title = typeof metadata.name === 'string' ? metadata.name : '';
  const timeLimit = asOptionalNumber(problem.time_limit);
  const spaceLimit = asOptionalNumber(problem.space_limit);
  const parsed = parseSections(description);

  if (!parsed.hasStructure) {
    return {
      title,
      bodySections: description
        ? [{ heading: '', content: description }]
        : [],
      inputFormat: '',
      outputFormat: '',
      constraints: '',
      complexity: '',
      explanation: '',
      samples: buildFallbackSamples(problem.public_tests),
      meta: {
        ...metadata,
        timeLimit,
        spaceLimit,
        usedFallback: true,
      },
    };
  }

  let inputFormat = '';
  let outputFormat = '';
  let constraints = '';
  let complexity = '';
  let explanation = '';
  const bodySections: ProblemStatementSection[] = [];
  const sampleContent = buildSamples(parsed.sections);
  const fallbackSamples = buildFallbackSamples(problem.public_tests);
  const sampleUsedFallback = sampleContent.samples.length === 0 && fallbackSamples.length > 0;

  for (const section of parsed.sections) {
    if (!section.content) continue;

    if (section.type === 'problem' || section.type === 'unknown') {
      bodySections.push({
        heading: section.heading,
        content: section.content,
      });
      continue;
    }

    if (section.type === 'input') {
      inputFormat = appendText(inputFormat, section.content);
      continue;
    }

    if (section.type === 'output') {
      outputFormat = appendText(outputFormat, section.content);
      continue;
    }

    if (section.type === 'constraints') {
      constraints = appendText(constraints, section.content);
      continue;
    }

    if (section.type === 'complexity') {
      complexity = appendText(complexity, section.content);
      continue;
    }

    if (section.type === 'explanation') {
      explanation = appendText(explanation, section.content);
    }
  }

  bodySections.push(...sampleContent.readableSections);

  return {
    title,
    bodySections,
    inputFormat,
    outputFormat,
    constraints,
    complexity,
    explanation,
    samples: sampleContent.samples.length > 0 ? sampleContent.samples : fallbackSamples,
    meta: {
      ...metadata,
      timeLimit,
      spaceLimit,
      usedFallback: sampleUsedFallback,
    },
  };
}
