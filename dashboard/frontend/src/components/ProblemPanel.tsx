import { useCallback, useDeferredValue, useEffect, useMemo, useState } from 'react';

interface ProblemSummary {
  id: string;
  name: string;
  source: string;
  family?: string;
  difficulty: number | string;
  is_custom?: boolean;
  is_showcase?: boolean;
  preview: string;
}

interface CodeforcesResult {
  contest_id: number;
  index: string;
  name: string;
  rating: number | null;
  tags: string[];
  url: string;
  problem_id: string;
}

interface CustomTestDraft {
  id: string;
  input: string;
  output: string;
}

interface ProblemPanelProps {
  onSubmit: (problem: Record<string, unknown>, config: Record<string, unknown>) => Promise<boolean>;
  onClose: () => void;
}

type PanelTab = 'browse' | 'custom' | 'manage' | 'codeforces';

function readErrorMessage(data: Record<string, unknown>, fallback: string): string {
  const detail = data.detail;
  if (typeof detail === 'string' && detail.trim()) {
    return detail;
  }
  const error = data.error;
  if (typeof error === 'string' && error.trim()) {
    return error;
  }
  return fallback;
}

async function readJsonRecord(response: Response): Promise<Record<string, unknown>> {
  try {
    const data = await response.json() as unknown;
    if (data && typeof data === 'object') {
      return data as Record<string, unknown>;
    }
  } catch {
    // Ignore malformed JSON and fall back to a generic error.
  }
  return {};
}

async function readJsonOrThrow(response: Response, fallback: string): Promise<Record<string, unknown>> {
  const data = await readJsonRecord(response);
  if (!response.ok) {
    throw new Error(readErrorMessage(data, fallback));
  }
  return data;
}

function createTestDraft(): CustomTestDraft {
  return {
    id: `test-${Math.random().toString(36).slice(2, 10)}`,
    input: '',
    output: '',
  };
}

function formatDifficulty(value: number | string): string | null {
  if (typeof value === 'number') {
    return value > 0 ? `difficulty ${value}` : null;
  }
  const normalized = value.trim();
  return normalized ? normalized : null;
}

function slugify(value: string, fallback = 'custom-live'): string {
  const slug = value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return slug || fallback;
}

function buildCustomProblemPayload(input: {
  title: string;
  description: string;
  source: string;
  difficulty: string;
  constraintsText: string;
  timeLimitMs: string;
  memoryLimitMb: string;
  publicTests: Array<{ input: string; output: string }>;
}): Record<string, unknown> {
  const normalizedTitle = input.title.trim() || 'Untitled Custom Problem';
  const normalizedDescription = input.description.trim();
  const normalizedConstraints = input.constraintsText.trim();
  const description = normalizedConstraints
    ? `${normalizedDescription}\n\nConstraints\n${normalizedConstraints}`
    : normalizedDescription;
  const problemId = `custom_${slugify(normalizedTitle)}`;

  return {
    problem_id: problemId,
    description,
    public_tests: input.publicTests,
    constraints: normalizedConstraints ? { raw: normalizedConstraints } : {},
    time_limit: input.timeLimitMs ? Number(input.timeLimitMs) : null,
    space_limit: input.memoryLimitMb ? Number(input.memoryLimitMb) : null,
    types: [],
    _metadata: {
      source: input.source.trim() || 'custom',
      platform: 'custom',
      question_id: problemId,
      name: normalizedTitle,
      difficulty: input.difficulty.trim() || 'custom',
      custom: true,
    },
  };
}

function removeAppendedConstraints(description: string, constraintsRaw: string): string {
  const suffix = `\n\nConstraints\n${constraintsRaw}`;
  return description.endsWith(suffix) ? description.slice(0, -suffix.length) : description;
}

export default function ProblemPanel({ onSubmit, onClose }: ProblemPanelProps) {
  const [tab, setTab] = useState<PanelTab>('browse');
  const [problems, setProblems] = useState<ProblemSummary[]>([]);
  const [search, setSearch] = useState('');
  const [codeforcesQuery, setCodeforcesQuery] = useState('');
  const [codeforcesResults, setCodeforcesResults] = useState<CodeforcesResult[]>([]);
  const [codeforcesSearchLoading, setCodeforcesSearchLoading] = useState(false);
  const [codeforcesImportId, setCodeforcesImportId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [manageSelectedId, setManageSelectedId] = useState<string | null>(null);
  const [editingProblemId, setEditingProblemId] = useState<string | null>(null);
  const [customTitle, setCustomTitle] = useState('');
  const [customSource, setCustomSource] = useState('custom');
  const [customDifficulty, setCustomDifficulty] = useState('');
  const [customDesc, setCustomDesc] = useState('');
  const [constraintsText, setConstraintsText] = useState('');
  const [timeLimitMs, setTimeLimitMs] = useState('2000');
  const [memoryLimitMb, setMemoryLimitMb] = useState('256');
  const [customTests, setCustomTests] = useState<CustomTestDraft[]>([createTestDraft()]);
  const [saveToLibrary, setSaveToLibrary] = useState(true);
  const [maxIter, setMaxIter] = useState(5);
  const [loading, setLoading] = useState(false);
  const [manageLoadingId, setManageLoadingId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const deferredSearch = useDeferredValue(search);

  const loadProblems = useCallback(() => {
    fetch('/api/problems')
      .then((response) => readJsonOrThrow(response, 'Failed to load problem library'))
      .then((data) => setProblems(Array.isArray(data.problems) ? data.problems as ProblemSummary[] : []))
      .catch((error: unknown) => {
        setErrorMessage(error instanceof Error ? error.message : 'Failed to load problem library');
      });
  }, []);

  useEffect(() => {
    loadProblems();
  }, [loadProblems]);

  const resetCustomForm = useCallback(() => {
    setEditingProblemId(null);
    setCustomTitle('');
    setCustomSource('custom');
    setCustomDifficulty('');
    setCustomDesc('');
    setConstraintsText('');
    setTimeLimitMs('2000');
    setMemoryLimitMb('256');
    setCustomTests([createTestDraft()]);
    setSaveToLibrary(true);
    setErrorMessage(null);
  }, []);

  const filtered = useMemo(() => {
    const normalizedQuery = deferredSearch.trim().toLowerCase();
    const ranked = [...problems].sort((left, right) => {
      const showcaseDelta = Number(Boolean(right.is_showcase)) - Number(Boolean(left.is_showcase));
      if (showcaseDelta !== 0) return showcaseDelta;
      return Number(Boolean(right.is_custom)) - Number(Boolean(left.is_custom));
    });
    return ranked.filter((problem) =>
      !normalizedQuery
      || problem.name.toLowerCase().includes(normalizedQuery)
      || problem.source.toLowerCase().includes(normalizedQuery)
      || (problem.family || '').toLowerCase().includes(normalizedQuery)
    );
  }, [deferredSearch, problems]);

  const savedCustomProblems = useMemo(
    () => filtered.filter((problem) => problem.is_custom),
    [filtered]
  );

  useEffect(() => {
    if (tab !== 'browse') return;
    if (selectedId && filtered.some((problem) => problem.id === selectedId)) return;
    setSelectedId(filtered[0]?.id || null);
  }, [filtered, selectedId, tab]);

  useEffect(() => {
    if (tab !== 'manage') return;
    if (manageSelectedId && savedCustomProblems.some((problem) => problem.id === manageSelectedId)) return;
    setManageSelectedId(savedCustomProblems[0]?.id || null);
  }, [manageSelectedId, savedCustomProblems, tab]);

  const selectedProblem = filtered.find((problem) => problem.id === selectedId) || null;
  const managedProblem = savedCustomProblems.find((problem) => problem.id === manageSelectedId) || null;
  const nonEmptyPublicTests = customTests
    .map((test) => ({ input: test.input.trim(), output: test.output.trim() }))
    .filter((test) => test.input || test.output);

  const populateFromProblem = useCallback((problem: Record<string, unknown>, filename: string | null) => {
    const metadata = ((problem._metadata as Record<string, unknown> | undefined) || {});
    const rawConstraints = typeof (problem.constraints as Record<string, unknown> | undefined)?.raw === 'string'
      ? ((problem.constraints as Record<string, unknown>).raw as string)
      : '';
    const description = typeof problem.description === 'string'
      ? removeAppendedConstraints(problem.description as string, rawConstraints)
      : '';

    setEditingProblemId(filename);
    setCustomTitle(String(metadata.name || ''));
    setCustomSource(String(metadata.source || 'custom'));
    setCustomDifficulty(String(metadata.difficulty || ''));
    setCustomDesc(description);
    setConstraintsText(rawConstraints);
    setTimeLimitMs(problem.time_limit ? String(problem.time_limit) : '2000');
    setMemoryLimitMb(problem.space_limit ? String(problem.space_limit) : '256');
    const tests = Array.isArray(problem.public_tests) ? problem.public_tests as Array<Record<string, unknown>> : [];
    setCustomTests(
      tests.length > 0
        ? tests.map((test, index) => ({
            id: `loaded-${index}-${Math.random().toString(36).slice(2, 8)}`,
            input: String(test.input || ''),
            output: String(test.output || ''),
          }))
        : [createTestDraft()]
    );
    setSaveToLibrary(true);
  }, []);

  const handleLoadCustomForEditing = useCallback(async (problemId: string) => {
    setErrorMessage(null);
    try {
      const response = await fetch(`/api/problems/${problemId}`);
      const problem = await readJsonOrThrow(response, 'Failed to load saved problem');
      populateFromProblem(problem, problemId);
      setTab('custom');
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to load saved problem');
    }
  }, [populateFromProblem]);

  const handleCloneCustomProblem = useCallback(async (problemId: string) => {
    setErrorMessage(null);
    try {
      const response = await fetch(`/api/problems/${problemId}`);
      const problem = await readJsonOrThrow(response, 'Failed to clone saved problem');
      populateFromProblem(problem, null);
      const metadata = ((problem._metadata as Record<string, unknown> | undefined) || {});
      setCustomTitle(`${String(metadata.name || 'Custom Problem')} Copy`);
      setEditingProblemId(null);
      setSaveToLibrary(true);
      setTab('custom');
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to clone saved problem');
    }
  }, [populateFromProblem]);

  const handleExportCustomProblem = useCallback(async (problemId: string) => {
    setErrorMessage(null);
    try {
      const response = await fetch(`/api/problems/${problemId}`);
      const problem = await readJsonOrThrow(response, 'Failed to export saved problem');
      const blob = new Blob([JSON.stringify(problem, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = problemId;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to export saved problem');
    }
  }, []);

  const handleSolveSavedProblem = useCallback(async (problemId: string) => {
    if (loading || manageLoadingId !== null) {
      return;
    }

    setErrorMessage(null);
    setManageLoadingId(problemId);
    try {
      const response = await fetch(`/api/problems/${problemId}`);
      const problem = await readJsonOrThrow(response, 'Failed to load saved problem');
      const started = await onSubmit(problem, { max_iterations: maxIter });
      if (!started) {
        setErrorMessage('Solve did not start. Please try again.');
      }
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to launch saved problem');
    } finally {
      setManageLoadingId(null);
    }
  }, [loading, manageLoadingId, maxIter, onSubmit]);

  const handleDeleteCustomProblem = useCallback(async (problemId: string) => {
    if (!window.confirm('Delete this saved custom problem from the local library?')) return;
    setErrorMessage(null);
    try {
      const response = await fetch(`/api/problems/custom/${problemId}`, { method: 'DELETE' });
      await readJsonOrThrow(response, 'Failed to delete saved problem');
      if (editingProblemId === problemId) {
        resetCustomForm();
      }
      if (manageSelectedId === problemId) {
        setManageSelectedId(null);
      }
      loadProblems();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to delete saved problem');
    }
  }, [editingProblemId, loadProblems, manageSelectedId, resetCustomForm]);

  const searchCodeforces = useCallback(async () => {
    if (!codeforcesQuery.trim() || codeforcesSearchLoading || codeforcesImportId !== null) {
      return;
    }

    setErrorMessage(null);
    setCodeforcesSearchLoading(true);
    try {
      const params = new URLSearchParams({
        q: codeforcesQuery.trim(),
        limit: '20',
      });
      const response = await fetch(`/api/sources/codeforces/search?${params.toString()}`);
      const data = await readJsonOrThrow(response, 'Failed to search Codeforces');
      setCodeforcesResults(Array.isArray(data.results) ? data.results as CodeforcesResult[] : []);
    } catch (error) {
      setCodeforcesResults([]);
      setErrorMessage(error instanceof Error ? error.message : 'Failed to search Codeforces');
    } finally {
      setCodeforcesSearchLoading(false);
    }
  }, [codeforcesImportId, codeforcesQuery, codeforcesSearchLoading]);

  const importAndSolveCodeforces = useCallback(async (result: CodeforcesResult) => {
    if (loading || manageLoadingId !== null || codeforcesImportId !== null) {
      return;
    }

    setErrorMessage(null);
    setCodeforcesImportId(result.problem_id);
    try {
      const response = await fetch('/api/sources/codeforces/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contest_id: result.contest_id,
          index: result.index,
          url: result.url,
        }),
      });
      const data = await readJsonOrThrow(response, 'Failed to import Codeforces problem');
      const importedProblem = data.problem;
      if (!importedProblem || typeof importedProblem !== 'object') {
        throw new Error('Imported Codeforces response is missing problem');
      }

      loadProblems();
      const started = await onSubmit(importedProblem as Record<string, unknown>, { max_iterations: maxIter });
      if (!started) {
        setErrorMessage('Solve did not start. Please try again.');
      }
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to import Codeforces problem');
    } finally {
      setCodeforcesImportId(null);
    }
  }, [codeforcesImportId, loadProblems, loading, manageLoadingId, maxIter, onSubmit]);

  const handleSubmit = async () => {
    if (loading || manageLoadingId !== null) {
      return;
    }

    setErrorMessage(null);
    setLoading(true);
    try {
      let problem: Record<string, unknown>;
      if (tab === 'browse' && selectedId) {
        const res = await fetch(`/api/problems/${selectedId}`);
        problem = await readJsonOrThrow(res, 'Failed to load selected problem');
      } else if (tab === 'custom' && customDesc.trim()) {
        const requestPayload = {
          title: customTitle.trim() || 'Untitled Custom Problem',
          description: customDesc.trim(),
          source: customSource.trim() || 'custom',
          difficulty: customDifficulty.trim() || 'custom',
          constraints_text: constraintsText.trim(),
          time_limit_ms: timeLimitMs ? Number(timeLimitMs) : null,
          memory_limit_mb: memoryLimitMb ? Number(memoryLimitMb) : null,
          public_tests: nonEmptyPublicTests,
        };

        if (saveToLibrary) {
          const method = editingProblemId ? 'PUT' : 'POST';
          const url = editingProblemId
            ? `/api/problems/custom/${editingProblemId}`
            : '/api/problems/custom';
          const saveResponse = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestPayload),
          });
          const saved = await readJsonOrThrow(saveResponse, 'Failed to save custom problem');
          const savedProblem = saved.problem;
          if (!savedProblem || typeof savedProblem !== 'object') {
            throw new Error('Saved custom problem response is missing problem');
          }
          problem = savedProblem as Record<string, unknown>;
          loadProblems();
          if (saved.filename) {
            setSelectedId(String(saved.filename));
            setManageSelectedId(String(saved.filename));
            setEditingProblemId(String(saved.filename));
          }
        } else {
          problem = buildCustomProblemPayload({
            title: requestPayload.title,
            description: requestPayload.description,
            source: requestPayload.source,
            difficulty: requestPayload.difficulty,
            constraintsText: requestPayload.constraints_text,
            timeLimitMs: timeLimitMs,
            memoryLimitMb: memoryLimitMb,
            publicTests: nonEmptyPublicTests,
          });
        }
      } else {
        return;
      }
      const started = await onSubmit(problem, { max_iterations: maxIter });
      if (!started) {
        setErrorMessage('Solve did not start. Please try again.');
      }
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Solve launch failed');
    } finally {
      setLoading(false);
    }
  };

  const canSubmit =
    (tab === 'browse' && selectedId !== null) ||
    (tab === 'custom' && customDesc.trim().length > 0);
  const submitDisabled = tab === 'manage' || loading || manageLoadingId !== null || !canSubmit;

  return (
    <div className="pp-overlay" onClick={onClose}>
      <div className="pp-modal" onClick={(event) => event.stopPropagation()}>
        <div className="pp-header">
          <div>
            <h2 className="pp-title">Start an AlgoPilot Run</h2>
            <p className="pp-subtitle">Choose a sample problem or build a custom one for AlgoPilot to solve.</p>
          </div>
          <button type="button" className="pp-close" onClick={onClose}>×</button>
        </div>

        <div className="pp-tabs">
          <button
            type="button"
            className={`pp-tab ${tab === 'browse' ? 'pp-tab--active' : ''}`}
            onClick={() => {
              setErrorMessage(null);
              setTab('browse');
            }}
          >
            AlgoPilot Library
          </button>
          <button
            type="button"
            className={`pp-tab ${tab === 'custom' ? 'pp-tab--active' : ''}`}
            onClick={() => {
              setErrorMessage(null);
              setTab('custom');
            }}
          >
            Custom Problem
          </button>
          <button
            type="button"
            className={`pp-tab ${tab === 'codeforces' ? 'pp-tab--active' : ''}`}
            onClick={() => {
              setErrorMessage(null);
              setTab('codeforces');
            }}
          >
            Codeforces
          </button>
          <button
            type="button"
            className={`pp-tab ${tab === 'manage' ? 'pp-tab--active' : ''}`}
            onClick={() => {
              setErrorMessage(null);
              setTab('manage');
            }}
          >
            Manage AlgoPilot Library
          </button>
        </div>

        <div className="pp-body">
          {tab !== 'codeforces' && (
            <div className="pp-toolbar">
              <input
                className="pp-search"
                type="text"
                placeholder={tab === 'manage' ? 'Search saved custom problems...' : 'Search by name or source...'}
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
              <div className="pp-stats">
                <span>{problems.length} samples</span>
                <span>{savedCustomProblems.length} saved custom</span>
              </div>
            </div>
          )}

          {tab === 'browse' && (
            <div className="pp-browse">
              <div className="pp-list">
                {filtered.map((problem) => {
                  const difficultyLabel = formatDifficulty(problem.difficulty);
                  return (
                    <button
                      key={problem.id}
                      type="button"
                      className={`pp-item ${selectedId === problem.id ? 'pp-item--selected' : ''}`}
                      aria-pressed={selectedId === problem.id}
                      onClick={() => setSelectedId(problem.id)}
                    >
                      <div className="pp-item__top">
                        <span className="pp-item__name">{problem.name}</span>
                        <span className="pp-item__badge">{problem.source}</span>
                        {problem.family && <span className="pp-item__family">{problem.family}</span>}
                        {problem.is_showcase && <span className="pp-item__showcase">showcase</span>}
                        {problem.is_custom && <span className="pp-item__custom">saved</span>}
                        {difficultyLabel && (
                          <span className="pp-item__diff">{difficultyLabel}</span>
                        )}
                      </div>
                      <div className="pp-item__preview">{problem.preview}</div>
                    </button>
                  );
                })}
                {filtered.length === 0 && (
                  <div className="pp-empty">No problems found</div>
                )}
              </div>

              <div className="pp-preview">
                <div className="pp-preview__kicker">Selected Problem</div>
                {selectedProblem ? (
                  <>
                    <h3 className="pp-preview__title">{selectedProblem.name}</h3>
                      <div className="pp-preview__chips">
                        <span className="pp-preview__chip">{selectedProblem.source}</span>
                        {selectedProblem.family && <span className="pp-preview__chip">{selectedProblem.family}</span>}
                        {selectedProblem.is_showcase && <span className="pp-preview__chip">showcase</span>}
                        {selectedProblem.is_custom && <span className="pp-preview__chip">saved custom</span>}
                        {formatDifficulty(selectedProblem.difficulty) && (
                          <span className="pp-preview__chip">{formatDifficulty(selectedProblem.difficulty)}</span>
                      )}
                    </div>
                    <p className="pp-preview__text">{selectedProblem.preview}</p>
                    <div className="pp-preview__hint">
                      Launching from the library uses the stored statement and built-in public samples.
                    </div>
                  </>
                ) : (
                  <p className="pp-empty">Choose a problem to preview it here.</p>
                )}
              </div>
            </div>
          )}

          {tab === 'custom' && (
            <div className="pp-custom">
              <div className="pp-custom__header">
                <div>
                  <div className="pp-preview__kicker">Custom Authoring</div>
                  <p className="pp-tests__hint">
                    {editingProblemId
                      ? `Editing saved problem ${editingProblemId}`
                      : 'Build a structured custom problem, optionally save it, then launch the run.'}
                  </p>
                </div>
                {editingProblemId && (
                  <button
                    type="button"
                    className="pp-tests__add"
                    onClick={resetCustomForm}
                  >
                    + New Blank Problem
                  </button>
                )}
              </div>

              <div className="pp-custom__grid">
                <label className="pp-field">
                  <span className="pp-field__label">Title</span>
                  <input
                    className="pp-input"
                    type="text"
                    placeholder="e.g. Minimum Segment Covers"
                    value={customTitle}
                    onChange={(event) => setCustomTitle(event.target.value)}
                  />
                </label>
                <label className="pp-field">
                  <span className="pp-field__label">Source Label</span>
                  <input
                    className="pp-input"
                    type="text"
                    placeholder="custom / interview / contest"
                    value={customSource}
                    onChange={(event) => setCustomSource(event.target.value)}
                  />
                </label>
                <label className="pp-field">
                  <span className="pp-field__label">Difficulty</span>
                  <input
                    className="pp-input"
                    type="text"
                    placeholder="easy / medium / hard"
                    value={customDifficulty}
                    onChange={(event) => setCustomDifficulty(event.target.value)}
                  />
                </label>
                <label className="pp-field">
                  <span className="pp-field__label">Time Limit (ms)</span>
                  <input
                    className="pp-input"
                    type="number"
                    min={1}
                    value={timeLimitMs}
                    onChange={(event) => setTimeLimitMs(event.target.value)}
                  />
                </label>
                <label className="pp-field">
                  <span className="pp-field__label">Memory Limit (MB)</span>
                  <input
                    className="pp-input"
                    type="number"
                    min={1}
                    value={memoryLimitMb}
                    onChange={(event) => setMemoryLimitMb(event.target.value)}
                  />
                </label>
              </div>

              <label className="pp-field">
                <span className="pp-field__label">Problem Statement</span>
                <textarea
                  className="pp-textarea pp-textarea--statement"
                  placeholder="Paste the full statement here..."
                  value={customDesc}
                  onChange={(event) => setCustomDesc(event.target.value)}
                />
              </label>

              <label className="pp-field">
                <span className="pp-field__label">Constraints / Notes</span>
                <textarea
                  className="pp-textarea pp-textarea--constraints"
                  placeholder="Optional: list numeric bounds, edge conditions, or notes you want the agent to see clearly."
                  value={constraintsText}
                  onChange={(event) => setConstraintsText(event.target.value)}
                />
              </label>

              <div className="pp-tests">
                <div className="pp-tests__head">
                  <div>
                    <div className="pp-preview__kicker">Public Tests</div>
                    <p className="pp-tests__hint">Add any sample cases you want the agent to use as trusted starter tests.</p>
                  </div>
                  <button
                    className="pp-tests__add"
                    type="button"
                    onClick={() => setCustomTests((prev) => [...prev, createTestDraft()])}
                  >
                    + Add Test
                  </button>
                </div>
                <div className="pp-tests__list">
                  {customTests.map((test, index) => (
                    <div key={test.id} className="pp-testCard">
                      <div className="pp-testCard__head">
                        <span>Sample {index + 1}</span>
                        {customTests.length > 1 && (
                          <button
                            className="pp-testCard__remove"
                            type="button"
                            onClick={() => setCustomTests((prev) => prev.filter((item) => item.id !== test.id))}
                          >
                            Remove
                          </button>
                        )}
                      </div>
                      <div className="pp-testCard__grid">
                        <label className="pp-field">
                          <span className="pp-field__label">Input</span>
                          <textarea
                            className="pp-textarea pp-textarea--test"
                            placeholder="Sample input"
                            value={test.input}
                            onChange={(event) => {
                              const value = event.target.value;
                              setCustomTests((prev) => prev.map((item) => item.id === test.id ? { ...item, input: value } : item));
                            }}
                          />
                        </label>
                        <label className="pp-field">
                          <span className="pp-field__label">Expected Output</span>
                          <textarea
                            className="pp-textarea pp-textarea--test"
                            placeholder="Expected output"
                            value={test.output}
                            onChange={(event) => {
                              const value = event.target.value;
                              setCustomTests((prev) => prev.map((item) => item.id === test.id ? { ...item, output: value } : item));
                            }}
                          />
                        </label>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="pp-custom__meta">
                <label className="pp-checkbox">
                  <input
                    type="checkbox"
                    checked={saveToLibrary}
                    onChange={(event) => setSaveToLibrary(event.target.checked)}
                  />
                  <span>Save this custom problem into the local library before solving</span>
                </label>
                <span>{customDesc.trim().length} chars • {nonEmptyPublicTests.length} test case(s)</span>
              </div>
            </div>
          )}

          {tab === 'codeforces' && (
            <div className="pp-codeforces">
              <div className="pp-tests">
                <div className="pp-tests__head">
                  <div>
                    <div className="pp-preview__kicker">Codeforces Import</div>
                    <p className="pp-tests__hint">
                      Search by contest/index or title, then import the selected problem into the local library and solve it.
                    </p>
                  </div>
                </div>

                <label className="pp-field">
                  <span className="pp-field__label">Search Codeforces</span>
                  <div className="pp-codeforces__controls">
                    <input
                      aria-label="Search Codeforces"
                      className="pp-input"
                      type="text"
                      placeholder="e.g. 1575 C or Cyclic Sum"
                      value={codeforcesQuery}
                      onChange={(event) => setCodeforcesQuery(event.target.value)}
                    />
                    <button
                      type="button"
                      className="pp-tests__add"
                      disabled={codeforcesSearchLoading || codeforcesImportId !== null || !codeforcesQuery.trim()}
                      onClick={searchCodeforces}
                    >
                      {codeforcesSearchLoading ? 'Searching...' : 'Search'}
                    </button>
                  </div>
                </label>

                <div className="pp-codeforces__results" role="list" aria-label="Codeforces Results">
                  {codeforcesResults.map((result) => (
                    <div key={result.problem_id} className="pp-codeforcesCard" role="listitem">
                      <div className="pp-item__top">
                        <span className="pp-item__name">{result.name}</span>
                        <span className="pp-item__badge">Codeforces</span>
                        <span className="pp-item__family">
                          {result.contest_id}
                          {result.index}
                        </span>
                        {typeof result.rating === 'number' && (
                          <span className="pp-item__diff">rating {result.rating}</span>
                        )}
                      </div>
                      <div className="pp-item__preview">{result.problem_id}</div>
                      {result.tags.length > 0 && (
                        <div className="pp-preview__chips">
                          {result.tags.slice(0, 4).map((tag) => (
                            <span key={`${result.problem_id}-${tag}`} className="pp-preview__chip">
                              {tag}
                            </span>
                          ))}
                        </div>
                      )}
                      <div className="pp-codeforcesCard__actions">
                        <button
                          type="button"
                          className="pp-manageActions__secondary"
                          disabled={loading || manageLoadingId !== null || codeforcesImportId !== null}
                          onClick={() => importAndSolveCodeforces(result)}
                        >
                          {codeforcesImportId === result.problem_id ? 'Importing...' : 'Import and Solve'}
                        </button>
                      </div>
                    </div>
                  ))}
                  {!codeforcesSearchLoading && codeforcesResults.length === 0 && (
                    <div className="pp-empty">Search Codeforces to import a problem.</div>
                  )}
                </div>
              </div>
            </div>
          )}

          {tab === 'manage' && (
            <div className="pp-browse">
              <div className="pp-list">
                {savedCustomProblems.map((problem) => (
                  <button
                    key={problem.id}
                    type="button"
                    className={`pp-item ${manageSelectedId === problem.id ? 'pp-item--selected' : ''}`}
                    aria-pressed={manageSelectedId === problem.id}
                    onClick={() => setManageSelectedId(problem.id)}
                  >
                    <div className="pp-item__top">
                      <span className="pp-item__name">{problem.name}</span>
                      <span className="pp-item__badge">{problem.source}</span>
                      <span className="pp-item__custom">saved</span>
                    </div>
                    <div className="pp-item__preview">{problem.preview}</div>
                  </button>
                ))}
                {savedCustomProblems.length === 0 && (
                  <div className="pp-empty">No saved custom problems yet.</div>
                )}
              </div>

              <div className="pp-preview">
                <div className="pp-preview__kicker">Library Actions</div>
                {managedProblem ? (
                  <>
                    <h3 className="pp-preview__title">{managedProblem.name}</h3>
                    <div className="pp-preview__chips">
                      <span className="pp-preview__chip">{managedProblem.source}</span>
                      <span className="pp-preview__chip">saved custom</span>
                      {formatDifficulty(managedProblem.difficulty) && (
                        <span className="pp-preview__chip">{formatDifficulty(managedProblem.difficulty)}</span>
                      )}
                    </div>
                    <p className="pp-preview__text">{managedProblem.preview}</p>
                    <div className="pp-manageActions">
                      <button
                        type="button"
                        className="pp-manageActions__primary"
                        disabled={loading || manageLoadingId !== null}
                        onClick={() => handleLoadCustomForEditing(managedProblem.id)}
                      >
                        Rename / Edit
                      </button>
                      <button
                        type="button"
                        className="pp-manageActions__secondary"
                        disabled={loading || manageLoadingId !== null}
                        onClick={() => handleSolveSavedProblem(managedProblem.id)}
                      >
                        {manageLoadingId === managedProblem.id ? 'Starting...' : 'Solve Now'}
                      </button>
                      <button
                        type="button"
                        className="pp-manageActions__secondary"
                        disabled={loading || manageLoadingId !== null}
                        onClick={() => handleCloneCustomProblem(managedProblem.id)}
                      >
                        Clone
                      </button>
                      <button
                        type="button"
                        className="pp-manageActions__secondary"
                        disabled={loading || manageLoadingId !== null}
                        onClick={() => handleExportCustomProblem(managedProblem.id)}
                      >
                        Export JSON
                      </button>
                      <button
                        type="button"
                        className="pp-manageActions__danger"
                        disabled={loading || manageLoadingId !== null}
                        onClick={() => handleDeleteCustomProblem(managedProblem.id)}
                      >
                        Delete
                      </button>
                    </div>
                  </>
                ) : (
                  <p className="pp-empty">Select a saved custom problem to edit, solve, or delete it.</p>
                )}
              </div>
            </div>
          )}
        </div>

        {errorMessage && (
          <div className="pp-error" role="alert">
            {errorMessage}
          </div>
        )}

        <div className="pp-footer">
          <div className="pp-config">
            <label className="pp-config__label">Max Iterations</label>
            <input
              className="pp-config__input"
              type="number"
              min={1}
              max={20}
              value={maxIter}
              onChange={(event) => setMaxIter(Number(event.target.value))}
            />
          </div>
          <button
            className="pp-submit"
            disabled={submitDisabled}
            onClick={handleSubmit}
          >
            {loading ? 'Starting...' : editingProblemId && saveToLibrary && tab === 'custom'
              ? 'Update & Start Solve'
              : saveToLibrary && tab === 'custom'
                ? 'Save & Start Solve'
                : 'Start Solve'}
          </button>
        </div>
      </div>

      <style>{`
        .pp-overlay {
          position: fixed;
          inset: 0;
          z-index: 1000;
          display: flex;
          align-items: center;
          justify-content: center;
          background: rgba(0, 0, 0, 0.6);
          backdrop-filter: blur(6px);
          animation: fade-in 0.2s ease;
        }
        .pp-modal {
          width: 1080px;
          max-width: 94vw;
          max-height: 90vh;
          display: flex;
          flex-direction: column;
          background: linear-gradient(180deg, rgba(14, 19, 28, 0.98), rgba(7, 11, 17, 0.96));
          border: 1px solid var(--color-border-glass);
          border-radius: 24px;
          box-shadow: var(--shadow-md);
          overflow: hidden;
          animation: slide-in-right 0.2s ease;
        }
        .pp-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 24px 28px 14px;
        }
        .pp-title {
          font-size: 28px;
          font-weight: 700;
          color: var(--color-text-primary);
        }
        .pp-subtitle {
          margin-top: 6px;
          font-size: var(--font-size-sm);
          color: var(--color-text-secondary);
        }
        .pp-close {
          background: none;
          border: none;
          color: var(--color-text-muted);
          font-size: 24px;
          cursor: pointer;
          padding: 4px 8px;
          border-radius: 8px;
          transition: all var(--transition-fast);
        }
        .pp-close:hover {
          color: var(--color-text-primary);
          background: var(--color-bg-elevated);
        }
        .pp-tabs {
          display: flex;
          gap: 0;
          padding: 0 28px;
          border-bottom: 1px solid var(--color-border-subtle);
        }
        .pp-tab {
          background: none;
          border: none;
          padding: 12px 20px;
          font-size: var(--font-size-sm);
          font-weight: 600;
          color: var(--color-text-muted);
          cursor: pointer;
          border-bottom: 2px solid transparent;
          transition: all var(--transition-fast);
        }
        .pp-tab:hover {
          color: var(--color-text-secondary);
        }
        .pp-tab--active {
          color: var(--color-accent-blue);
          border-bottom-color: var(--color-accent-blue);
        }
        .pp-body {
          flex: 1;
          padding: 18px 28px;
          overflow-y: auto;
          min-height: 320px;
        }
        .pp-toolbar {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          margin-bottom: 14px;
        }
        .pp-search,
        .pp-input {
          width: 100%;
          padding: 12px 14px;
          background: var(--color-bg-glass);
          border: 1px solid var(--color-border-glass);
          border-radius: 14px;
          color: var(--color-text-primary);
          font-size: var(--font-size-sm);
          outline: none;
          transition: border-color var(--transition-fast);
        }
        .pp-search:focus,
        .pp-input:focus {
          border-color: var(--color-accent-blue);
        }
        .pp-search::placeholder,
        .pp-input::placeholder {
          color: var(--color-text-muted);
        }
        .pp-stats {
          display: flex;
          gap: 8px;
          flex-wrap: wrap;
          color: var(--color-text-secondary);
          font-size: 12px;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          white-space: nowrap;
        }
        .pp-browse {
          display: grid;
          grid-template-columns: minmax(0, 1.2fr) minmax(260px, 0.8fr);
          gap: 16px;
        }
        .pp-list {
          display: flex;
          flex-direction: column;
          gap: 8px;
          max-height: 500px;
          overflow-y: auto;
          padding-right: 4px;
        }
        .pp-item {
          width: 100%;
          text-align: left;
          padding: 14px;
          background: rgba(255,255,255,0.04);
          border: 1px solid var(--color-border-subtle);
          border-radius: 16px;
          cursor: pointer;
          transition: all var(--transition-fast);
        }
        .pp-item:hover {
          border-color: var(--color-border-hover);
          background: var(--color-bg-elevated);
        }
        .pp-item--selected {
          border-color: var(--color-accent-blue);
          background: rgba(64, 139, 255, 0.08);
          box-shadow: 0 12px 26px rgba(64, 139, 255, 0.12);
        }
        .pp-item:focus-visible {
          outline: 2px solid rgba(64, 139, 255, 0.48);
          outline-offset: 2px;
        }
        .pp-item__top {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 6px;
          flex-wrap: wrap;
        }
        .pp-item__name {
          font-size: 15px;
          font-weight: 600;
          color: var(--color-text-primary);
        }
        .pp-item__badge,
        .pp-item__family,
        .pp-item__showcase,
        .pp-item__custom {
          font-size: 10px;
          font-weight: 700;
          padding: 3px 7px;
          border-radius: 999px;
          text-transform: uppercase;
          letter-spacing: 0.08em;
        }
        .pp-item__badge {
          background: rgba(156, 122, 255, 0.15);
          color: var(--color-accent-purple);
        }
        .pp-item__family {
          background: rgba(64, 139, 255, 0.15);
          color: var(--color-accent-blue);
        }
        .pp-item__showcase {
          background: rgba(83, 208, 168, 0.15);
          color: var(--color-accent-green);
        }
        .pp-item__custom {
          background: rgba(83, 208, 168, 0.15);
          color: var(--color-accent-green);
        }
        .pp-item__diff {
          font-size: 11px;
          color: var(--color-accent-amber);
        }
        .pp-item__preview {
          font-size: 12px;
          color: var(--color-text-muted);
          line-height: 1.5;
        }
        .pp-preview {
          padding: 18px;
          border-radius: 20px;
          background: linear-gradient(180deg, rgba(64, 139, 255, 0.09), rgba(64, 139, 255, 0.03));
          border: 1px solid rgba(64, 139, 255, 0.14);
          min-height: 240px;
        }
        .pp-error {
          margin: 0 28px;
          padding: 12px 14px;
          border-radius: 14px;
          border: 1px solid rgba(247, 93, 93, 0.24);
          background: rgba(247, 93, 93, 0.12);
          color: var(--color-text-primary);
          font-size: 13px;
        }
        .pp-preview__kicker {
          font-size: 11px;
          font-weight: 700;
          letter-spacing: 0.12em;
          text-transform: uppercase;
          color: var(--color-text-muted);
        }
        .pp-preview__title {
          margin-top: 10px;
          font-size: 20px;
          font-weight: 700;
        }
        .pp-preview__chips {
          margin-top: 10px;
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }
        .pp-preview__chip {
          padding: 5px 10px;
          border-radius: 999px;
          background: rgba(255,255,255,0.08);
          color: var(--color-text-secondary);
          font-size: 11px;
          font-weight: 700;
          letter-spacing: 0.08em;
          text-transform: uppercase;
        }
        .pp-preview__text {
          margin-top: 14px;
          font-size: 14px;
          line-height: 1.65;
          color: var(--color-text-secondary);
        }
        .pp-preview__hint {
          margin-top: 14px;
          font-size: 13px;
          line-height: 1.6;
          color: var(--color-text-muted);
        }
        .pp-empty {
          text-align: center;
          color: var(--color-text-muted);
          font-size: var(--font-size-sm);
          padding: 40px 0;
          font-style: italic;
        }
        .pp-custom {
          display: grid;
          gap: 14px;
        }
        .pp-custom__header {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 12px;
        }
        .pp-custom__grid {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 12px;
        }
        .pp-field {
          display: grid;
          gap: 8px;
        }
        .pp-field__label {
          font-size: 11px;
          color: var(--color-text-muted);
          letter-spacing: 0.08em;
          text-transform: uppercase;
          font-weight: 700;
        }
        .pp-textarea {
          width: 100%;
          padding: 14px;
          background: var(--color-bg-glass);
          border: 1px solid var(--color-border-glass);
          border-radius: 16px;
          color: var(--color-text-primary);
          font-size: var(--font-size-sm);
          font-family: var(--font-mono);
          resize: vertical;
          outline: none;
          transition: border-color var(--transition-fast);
        }
        .pp-textarea:focus {
          border-color: var(--color-accent-blue);
        }
        .pp-textarea::placeholder {
          color: var(--color-text-muted);
        }
        .pp-textarea--statement {
          min-height: 220px;
        }
        .pp-textarea--constraints {
          min-height: 120px;
        }
        .pp-textarea--test {
          min-height: 120px;
        }
        .pp-tests {
          padding: 18px;
          border-radius: 20px;
          background: rgba(255,255,255,0.04);
          border: 1px solid rgba(255,255,255,0.06);
        }
        .pp-tests__head {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 12px;
        }
        .pp-tests__hint {
          margin-top: 6px;
          font-size: 13px;
          line-height: 1.6;
          color: var(--color-text-secondary);
        }
        .pp-tests__add {
          height: 36px;
          padding: 0 14px;
          border-radius: 999px;
          border: 1px solid rgba(64, 139, 255, 0.18);
          background: rgba(64, 139, 255, 0.12);
          color: var(--color-accent-blue);
          font-size: 12px;
          font-weight: 700;
          cursor: pointer;
        }
        .pp-tests__list {
          display: grid;
          gap: 12px;
          margin-top: 16px;
        }
        .pp-codeforces {
          display: grid;
          gap: 14px;
        }
        .pp-codeforces__controls {
          display: grid;
          grid-template-columns: minmax(0, 1fr) auto;
          gap: 12px;
          align-items: center;
        }
        .pp-codeforces__results {
          display: grid;
          gap: 12px;
          margin-top: 16px;
        }
        .pp-codeforcesCard {
          padding: 16px;
          border-radius: 18px;
          background: rgba(255,255,255,0.03);
          border: 1px solid rgba(255,255,255,0.06);
        }
        .pp-codeforcesCard__actions {
          display: flex;
          justify-content: flex-end;
          margin-top: 16px;
        }
        .pp-testCard {
          padding: 14px;
          border-radius: 18px;
          background: rgba(255,255,255,0.03);
          border: 1px solid rgba(255,255,255,0.05);
        }
        .pp-testCard__head {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 10px;
          margin-bottom: 12px;
          font-size: 13px;
          font-weight: 700;
          color: var(--color-text-primary);
        }
        .pp-testCard__remove {
          border: none;
          background: transparent;
          color: var(--color-accent-red);
          font-size: 12px;
          font-weight: 700;
          cursor: pointer;
        }
        .pp-testCard__grid {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 12px;
        }
        .pp-custom__meta {
          display: flex;
          justify-content: space-between;
          gap: 12px;
          color: var(--color-text-muted);
          font-size: 12px;
          line-height: 1.6;
        }
        .pp-checkbox {
          display: inline-flex;
          align-items: center;
          gap: 10px;
          color: var(--color-text-secondary);
        }
        .pp-checkbox input {
          accent-color: var(--color-accent-blue);
        }
        .pp-manageActions {
          display: flex;
          flex-wrap: wrap;
          gap: 10px;
          margin-top: 18px;
        }
        .pp-manageActions__primary,
        .pp-manageActions__secondary,
        .pp-manageActions__danger {
          height: 38px;
          padding: 0 16px;
          border-radius: 999px;
          border: none;
          font-size: 12px;
          font-weight: 700;
          cursor: pointer;
        }
        .pp-manageActions__primary:disabled,
        .pp-manageActions__secondary:disabled,
        .pp-manageActions__danger:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        .pp-manageActions__primary {
          background: rgba(64, 139, 255, 0.16);
          color: var(--color-accent-blue);
        }
        .pp-manageActions__secondary {
          background: rgba(83, 208, 168, 0.16);
          color: var(--color-accent-green);
        }
        .pp-manageActions__danger {
          background: rgba(247, 93, 93, 0.16);
          color: var(--color-accent-red);
        }
        .pp-footer {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 18px 28px;
          border-top: 1px solid var(--color-border-subtle);
        }
        .pp-config {
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .pp-config__label {
          font-size: var(--font-size-xs);
          color: var(--color-text-muted);
          text-transform: uppercase;
          letter-spacing: 0.06em;
        }
        .pp-config__input {
          width: 64px;
          padding: 8px 10px;
          background: var(--color-bg-glass);
          border: 1px solid var(--color-border-glass);
          border-radius: 12px;
          color: var(--color-text-primary);
          font-size: var(--font-size-sm);
          text-align: center;
          outline: none;
        }
        .pp-config__input:focus {
          border-color: var(--color-accent-blue);
        }
        .pp-submit {
          height: 44px;
          padding: 0 24px;
          background: linear-gradient(135deg, #408bff, #2c71f5);
          border: none;
          border-radius: 14px;
          color: white;
          font-size: var(--font-size-sm);
          font-weight: 700;
          cursor: pointer;
          transition: all var(--transition-fast);
        }
        .pp-submit:hover:not(:disabled) {
          opacity: 0.92;
          transform: translateY(-1px);
        }
        .pp-submit:disabled {
          opacity: 0.4;
          cursor: not-allowed;
        }
        @media (max-width: 960px) {
          .pp-browse,
          .pp-custom__grid,
          .pp-testCard__grid,
          .pp-codeforces__controls {
            grid-template-columns: 1fr;
          }
        }
        @media (max-width: 860px) {
          .pp-toolbar,
          .pp-footer,
          .pp-custom__meta,
          .pp-tests__head,
          .pp-custom__header {
            flex-direction: column;
            align-items: flex-start;
          }
          .pp-footer {
            gap: 12px;
          }
        }
      `}</style>
    </div>
  );
}
