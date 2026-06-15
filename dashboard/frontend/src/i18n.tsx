import { createContext, ReactNode, useContext, useMemo, useState } from 'react';

import type { AlgorithmVisualization } from './types/artifacts';
import type { LiveProgress } from './utils/buildLiveProgress';
import type {
  JourneyStageCard,
  JourneyStageId,
  JourneyStageStatus,
  JourneyStatusStrip,
  JourneyStep,
  JourneyTimelineEntry,
} from './types/journey';

export type DashboardLanguage = 'en' | 'zh';

type MessageKey = keyof typeof MESSAGES.en;

interface DashboardI18nContextValue {
  language: DashboardLanguage;
  setLanguage: (language: DashboardLanguage) => void;
  toggleLanguage: () => void;
  t: (key: MessageKey) => string;
}

const MESSAGES = {
  en: {
    languageToggleToZh: 'Switch language to Chinese',
    languageToggleToEn: 'Switch language to English',
    languageEnglishShort: 'EN',
    languageChineseShort: '中文',
    themeToggleToBright: 'Switch theme to bright',
    themeToggleToDark: 'Switch theme to dark',
    themeDarkShort: 'Dark',
    themeBrightShort: 'Bright',
    algoPilotSession: 'AlgoPilot Session',
    noActiveRun: 'No active run',
    noActiveProblem: 'No Active Problem',
    idle: 'idle',
    waitingForRun: 'Waiting for a run',
    restoringSavedSession: 'Restoring saved session',
    sessionHydrated: 'Session hydrated',
    savedRunMissing: 'Saved run missing',
    recoveryFailed: 'Recovery failed',
    interrupt: 'Interrupt',
    interrupting: 'Interrupting...',
    reconnect: 'Reconnect',
    resumeLatestRun: 'Resume Latest AlgoPilot Run',
    startSolve: 'Start Solve',
    currentRun: 'Current Run',
    pickProblemToBegin: 'Pick a sample or paste a custom problem to begin',
    journeyProgress: 'Journey Progress',
    waiting: 'Waiting',
    events: 'events',
    solveJourney: 'Solve Journey',
    solveJourneyTitle: 'Watch the solve as a guided four-stage trip',
    solveJourneyLiveLede: 'The map stays high-level on purpose: it shows where the run is now, what is already done, and which stages were skipped by strategy.',
    solveJourneyReplayLede: 'The map follows the replay cursor so you can see which fixed stage is active, complete, or still ahead.',
    journeyStatus: 'Journey Status',
    nextLikelyMove: 'Next Likely Move',
    stageWaiting: 'Stage: waiting',
    stagePrefix: 'Stage:',
    replayEvents: 'replay events',
    fineGrainedProgress: 'Fine-Grained Progress',
    iteration: 'Iteration',
    visibleTests: 'Visible Tests',
    result: 'Result',
    hackRound: 'Hack Round',
    runContext: 'AlgoPilot Run Context',
    abstractTags: 'Abstract tags',
    currentStage: 'Current stage',
    publicSamples: 'Public samples',
    playback: 'Playback',
    canonicalEvents: 'canonical events',
    algoPilotJourney: 'AlgoPilot Journey',
    touched: 'touched',
    finished: 'finished',
    ahead: 'ahead',
    problemPreview: 'Problem Preview',
    problemStatement: 'Problem Statement',
    inputFormat: 'Input Format',
    outputFormat: 'Output Format',
    constraints: 'Constraints',
    complexity: 'Complexity',
    explanation: 'Explanation',
    samples: 'Samples',
    input: 'Input',
    output: 'Output',
    finalSummary: 'Final Summary',
    completedRun: 'Completed Run',
    hackResult: 'Hack Result',
    turningPoints: 'Turning Points',
    timeline: 'Timeline',
    nothingYet: 'Nothing has happened yet',
    timelineEmpty: 'Start a solve or open a replay to watch the stage-by-stage story unfold here.',
    timelineTitle: 'Narrative view of the solve process',
    timelineReplayHint: 'Click a card to jump the replay cursor to that stage visit and expand its substeps.',
    timelineLiveHint: 'Click a card to expand its substeps and keep the detail panels aligned to the same stage.',
    stagePass: 'stage pass',
    substep: 'substep',
    substeps: 'substeps',
    evidencePoint: 'evidence point',
    evidencePoints: 'evidence points',
    runListTitle: 'AlgoPilot runs and replays',
    searchRuns: 'Search runs...',
    all: 'all',
    live: 'live',
    completed: 'completed',
    noRunsMatch: 'No runs match the current filter.',
    pass: 'pass',
    iters: 'iters',
    watch: 'Watch',
    watching: 'Watching',
    replay: 'Replay',
    opened: 'Opened',
    delete: 'Delete',
    deleteRunTitle: 'Delete this run record?',
    deleteRunBodySuffix: 'and removes the corresponding backend run file.',
    cancel: 'Cancel',
    deleting: 'Deleting...',
    deletePermanently: 'Delete Permanently',
    stageDetail: 'Stage Detail',
    selectStage: 'Select a stage to inspect it',
    stageDetailEmpty: 'The right rail explains what the currently selected stage is doing, why the workflow is in that stage, and what evidence matters most.',
    what: 'What',
    why: 'Why',
    evidence: 'Evidence',
    noExtraEvidence: 'This stage does not currently expose extra structured evidence in the event stream.',
    notVisitedYet: 'Not visited yet',
    later: 'Later',
    now: 'Now',
    done: 'Done',
    skipped: 'Skipped',
    repairing: 'Repairing',
    failed: 'Failed',
    idleStage: 'Idle',
    algorithmStory: 'Algorithm Story',
    teachingPlaybackUnavailable: 'Teaching playback is not available for this run',
    algorithmStoryUnsupportedPlaceholder: 'No family-level walkthrough is available for this problem.',
    algorithmStoryInsufficientTrace: 'Detected {family}, but this run did not generate enough process trace.',
    playbackDataMissing: 'This run does not contain step-by-step playback data yet.',
    publicSample: 'public sample',
    codeValidated: 'code-validated',
    codeMismatch: 'code mismatch',
    steps: 'steps',
    viewSampleIo: 'View sample input / output',
    sampleSource: 'Sample source',
    sampleFocus: 'Sample focus',
    sampleInput: 'Sample input',
    expectedOutput: 'Expected output',
    step: 'Step',
    noStepSelected: 'No step selected',
    stateChanges: 'State changes',
    continuousStep: 'This step mainly preserves the current state so the playback stays continuous.',
    prev: 'Prev',
    play: 'Play',
    pause: 'Pause',
    next: 'Next',
    replayProgress: 'Replay Progress',
    replayScrubTitle: 'Scrub the run by stage or exact event position',
    evidenceWorkbench: 'Evidence Workbench',
    evidenceWorkbenchTitle: 'Code, tests, result, and counterexamples in one place',
    problemPanelTitle: 'Start an AlgoPilot Run',
    problemPanelSubtitle: 'Choose a sample problem or build a custom one for AlgoPilot to solve.',
    problemPanelLibraryTab: 'AlgoPilot Library',
    problemPanelCustomProblem: 'Custom Problem',
    problemPanelManageLibraryTab: 'Manage AlgoPilot Library',
    problemPanelSearchPlaceholder: 'Search by name or source...',
    problemPanelSearchSavedPlaceholder: 'Search saved custom problems...',
    problemPanelSamplesCount: '{count} samples',
    problemPanelSavedCustomCount: '{count} saved custom',
    problemPanelDifficultyPrefix: 'difficulty',
    problemPanelShowcaseBadge: 'showcase',
    problemPanelSavedBadge: 'saved',
    problemPanelSavedCustomBadge: 'saved custom',
    problemPanelNoProblemsFound: 'No problems found',
    problemPanelSelectedProblem: 'Selected Problem',
    problemPanelLoadingPreview: 'Loading full statement preview...',
    problemPanelPreviewUnavailable: 'Full statement preview unavailable right now. You can still launch the saved problem.',
    problemPanelLibraryLaunchHint: 'Launching from the library uses the stored statement and built-in public samples.',
    problemPanelChoosePreview: 'Choose a problem to preview it here.',
    problemPanelCustomAuthoring: 'Custom Authoring',
    problemPanelEditingSavedProblem: 'Editing saved problem {id}',
    problemPanelCustomAuthoringHint: 'Build a structured custom problem, optionally save it, then launch the run.',
    problemPanelNewBlankProblem: '+ New Blank Problem',
    problemPanelFieldTitle: 'Title',
    problemPanelTitlePlaceholder: 'e.g. Minimum Segment Covers',
    problemPanelFieldSourceLabel: 'Source Label',
    problemPanelSourcePlaceholder: 'custom / interview / contest',
    problemPanelFieldDifficulty: 'Difficulty',
    problemPanelDifficultyPlaceholder: 'easy / medium / hard',
    problemPanelFieldTimeLimit: 'Time Limit (ms)',
    problemPanelFieldMemoryLimit: 'Memory Limit (MB)',
    problemPanelStatementPlaceholder: 'Paste the full statement here...',
    problemPanelFieldConstraintsNotes: 'Constraints / Notes',
    problemPanelConstraintsPlaceholder: 'Optional: list numeric bounds, edge conditions, or notes you want the agent to see clearly.',
    problemPanelPublicTests: 'Public Tests',
    problemPanelPublicTestsHint: 'Add any sample cases you want the agent to use as trusted starter tests.',
    problemPanelAddTest: '+ Add Test',
    problemPanelSampleNumber: 'Sample {number}',
    problemPanelRemove: 'Remove',
    problemPanelSaveCustomBeforeSolving: 'Save this custom problem into the local library before solving',
    problemPanelCustomMeta: '{chars} chars • {tests} test case(s)',
    problemPanelCodeforcesImport: 'Codeforces Import',
    problemPanelCodeforcesHint: 'Search by contest/index or title, then import the selected problem into the local library and solve it.',
    problemPanelSearchCodeforces: 'Search Codeforces',
    problemPanelSearching: 'Searching...',
    problemPanelSearch: 'Search',
    problemPanelCodeforcesResults: 'Codeforces Results',
    problemPanelRatingPrefix: 'rating',
    problemPanelImporting: 'Importing...',
    problemPanelImportAndSolve: 'Import and Solve',
    problemPanelSearchCodeforcesEmpty: 'Search Codeforces to import a problem.',
    problemPanelNoSavedCustom: 'No saved custom problems yet.',
    problemPanelLibraryActions: 'Library Actions',
    problemPanelRenameEdit: 'Rename / Edit',
    problemPanelStarting: 'Starting...',
    problemPanelSolveNow: 'Solve Now',
    problemPanelClone: 'Clone',
    problemPanelExportJson: 'Export JSON',
    problemPanelSelectSavedCustom: 'Select a saved custom problem to edit, solve, or delete it.',
    problemPanelMaxIterations: 'Max Iterations',
    problemPanelUpdateStartSolve: 'Update & Start Solve',
    problemPanelSaveStartSolve: 'Save & Start Solve',
    problemPanelUntitledCustomProblem: 'Untitled Custom Problem',
    problemPanelCopySuffix: 'Copy',
    problemPanelLoadLibraryFailed: 'Failed to load problem library',
    problemPanelLoadSelectedFailed: 'Failed to load selected problem',
    problemPanelLoadSavedFailed: 'Failed to load saved problem',
    problemPanelCloneSavedFailed: 'Failed to clone saved problem',
    problemPanelExportSavedFailed: 'Failed to export saved problem',
    problemPanelLaunchSavedFailed: 'Failed to launch saved problem',
    problemPanelDeleteConfirm: 'Delete this saved custom problem from the local library?',
    problemPanelDeleteSavedFailed: 'Failed to delete saved problem',
    problemPanelSearchCodeforcesFailed: 'Failed to search Codeforces',
    problemPanelImportCodeforcesFailed: 'Failed to import Codeforces problem',
    problemPanelSaveCustomFailed: 'Failed to save custom problem',
    problemPanelImportedMissingProblem: 'Imported Codeforces response is missing problem',
    problemPanelSavedMissingProblem: 'Saved custom problem response is missing problem',
    problemPanelSolveDidNotStart: 'Solve did not start. Please try again.',
    problemPanelSolveLaunchFailed: 'Solve launch failed',
  },
  zh: {
    languageToggleToZh: '切换语言为中文',
    languageToggleToEn: '切换语言为英文',
    languageEnglishShort: 'EN',
    languageChineseShort: '中文',
    themeToggleToBright: '切换风格为明亮',
    themeToggleToDark: '切换风格为深色',
    themeDarkShort: '深色',
    themeBrightShort: '明亮',
    algoPilotSession: 'AlgoPilot 会话',
    noActiveRun: '暂无运行',
    noActiveProblem: '暂无活跃题目',
    idle: '空闲',
    waitingForRun: '等待运行开始',
    restoringSavedSession: '正在恢复已保存会话',
    sessionHydrated: '会话已恢复',
    savedRunMissing: '保存的运行不存在',
    recoveryFailed: '恢复失败',
    interrupt: '中断',
    interrupting: '正在中断...',
    reconnect: '重新连接',
    resumeLatestRun: '恢复最近的 AlgoPilot 运行',
    startSolve: '开始求解',
    currentRun: '当前运行',
    pickProblemToBegin: '选择示例题或粘贴自定义题目开始',
    journeyProgress: '旅程进度',
    waiting: '等待中',
    events: '个事件',
    solveJourney: '求解旅程',
    solveJourneyTitle: '以四阶段引导旅程查看求解过程',
    solveJourneyLiveLede: '这张地图刻意保持高层视角：展示当前运行所在位置、已完成内容，以及被策略跳过的阶段。',
    solveJourneyReplayLede: '地图会跟随回放游标，帮助你查看固定阶段当前是活跃、完成还是仍在前方。',
    journeyStatus: '旅程状态',
    nextLikelyMove: '下一步可能动作',
    stageWaiting: '阶段：等待中',
    stagePrefix: '阶段：',
    replayEvents: '个回放事件',
    fineGrainedProgress: '细粒度进度',
    iteration: '迭代',
    visibleTests: '可见测试',
    result: '结果',
    hackRound: 'Hack 轮次',
    runContext: 'AlgoPilot 运行上下文',
    abstractTags: '抽象阶段标签',
    currentStage: '当前阶段',
    publicSamples: '公开样例',
    playback: '回放',
    canonicalEvents: '个标准事件',
    algoPilotJourney: 'AlgoPilot 旅程',
    touched: '已触达',
    finished: '已完成',
    ahead: '未开始',
    problemPreview: '题目预览',
    problemStatement: '题目描述',
    inputFormat: '输入格式',
    outputFormat: '输出格式',
    constraints: '约束条件',
    complexity: '复杂度',
    explanation: '说明',
    samples: '样例',
    input: '输入',
    output: '输出',
    finalSummary: '最终总结',
    completedRun: '已完成运行',
    hackResult: 'Hack 结果',
    turningPoints: '关键转折',
    timeline: '时间线',
    nothingYet: '尚未发生事件',
    timelineEmpty: '开始求解或打开回放后，可在这里查看逐阶段故事。',
    timelineTitle: '求解过程的叙事视图',
    timelineReplayHint: '点击卡片可将回放游标跳到该阶段访问，并展开子步骤。',
    timelineLiveHint: '点击卡片可展开子步骤，并让详情面板对齐到同一阶段。',
    stagePass: '阶段访问',
    substep: '个子步骤',
    substeps: '个子步骤',
    evidencePoint: '条证据',
    evidencePoints: '条证据',
    runListTitle: 'AlgoPilot 运行与回放',
    searchRuns: '搜索运行...',
    all: '全部',
    live: '实时',
    completed: '已完成',
    noRunsMatch: '没有运行匹配当前筛选条件。',
    pass: '通过率',
    iters: '迭代',
    watch: '观看',
    watching: '观看中',
    replay: '回放',
    opened: '已打开',
    delete: '删除',
    deleteRunTitle: '删除这条运行记录？',
    deleteRunBodySuffix: '并移除对应的后端运行文件。',
    cancel: '取消',
    deleting: '删除中...',
    deletePermanently: '永久删除',
    stageDetail: '阶段详情',
    selectStage: '选择一个阶段查看详情',
    stageDetailEmpty: '右侧栏会解释当前选中阶段正在做什么、为什么流程处于该阶段，以及哪些证据最关键。',
    what: '做什么',
    why: '为什么',
    evidence: '证据',
    noExtraEvidence: '该阶段当前没有在事件流中暴露额外结构化证据。',
    notVisitedYet: '尚未访问',
    later: '稍后',
    now: '当前',
    done: '完成',
    skipped: '已跳过',
    repairing: '修复中',
    failed: '失败',
    idleStage: '空闲',
    algorithmStory: '算法过程',
    teachingPlaybackUnavailable: '本次运行暂无教学回放',
    algorithmStoryUnsupportedPlaceholder: '该题暂无 family 级过程演示。',
    algorithmStoryInsufficientTrace: '已识别为 {family}，但本次运行未生成足够的过程轨迹。',
    playbackDataMissing: '本次运行还没有逐步回放数据。',
    publicSample: '公开样例',
    codeValidated: '代码已验证',
    codeMismatch: '代码输出不一致',
    steps: '步',
    viewSampleIo: '查看样例输入 / 输出',
    sampleSource: '样例来源',
    sampleFocus: '样例关注点',
    sampleInput: '样例输入',
    expectedOutput: '期望输出',
    step: '步骤',
    noStepSelected: '未选择步骤',
    stateChanges: '状态变化',
    continuousStep: '该步骤主要保持当前状态，让回放保持连续。',
    prev: '上一步',
    play: '播放',
    pause: '暂停',
    next: '下一步',
    replayProgress: '回放进度',
    replayScrubTitle: '按阶段或精确事件位置拖动回放',
    evidenceWorkbench: '证据工作台',
    evidenceWorkbenchTitle: '集中查看代码、测试、结果和反例',
    problemPanelTitle: '启动 AlgoPilot 运行',
    problemPanelSubtitle: '选择示例题，或创建自定义题目交给 AlgoPilot 求解。',
    problemPanelLibraryTab: 'AlgoPilot 题库',
    problemPanelCustomProblem: '自定义题目',
    problemPanelManageLibraryTab: '管理 AlgoPilot 题库',
    problemPanelSearchPlaceholder: '按名称或来源搜索...',
    problemPanelSearchSavedPlaceholder: '搜索已保存的自定义题...',
    problemPanelSamplesCount: '{count} 道示例题',
    problemPanelSavedCustomCount: '{count} 道已保存自定义题',
    problemPanelDifficultyPrefix: '难度',
    problemPanelShowcaseBadge: '展示题',
    problemPanelSavedBadge: '已保存',
    problemPanelSavedCustomBadge: '已保存自定义题',
    problemPanelNoProblemsFound: '未找到题目',
    problemPanelSelectedProblem: '已选择题目',
    problemPanelLoadingPreview: '正在加载完整题面预览...',
    problemPanelPreviewUnavailable: '当前无法预览完整题面。仍可启动这个已保存题目。',
    problemPanelLibraryLaunchHint: '从题库启动会使用已保存题面和内置公开样例。',
    problemPanelChoosePreview: '选择一道题后在这里预览。',
    problemPanelCustomAuthoring: '自定义编写',
    problemPanelEditingSavedProblem: '正在编辑已保存题目 {id}',
    problemPanelCustomAuthoringHint: '构建结构化自定义题，可选择保存后启动求解。',
    problemPanelNewBlankProblem: '+ 新建空白题目',
    problemPanelFieldTitle: '题目标题',
    problemPanelTitlePlaceholder: '例如：最少区间覆盖',
    problemPanelFieldSourceLabel: '来源标签',
    problemPanelSourcePlaceholder: '自定义 / 面试 / 比赛',
    problemPanelFieldDifficulty: '难度',
    problemPanelDifficultyPlaceholder: '简单 / 中等 / 困难',
    problemPanelFieldTimeLimit: '时间限制（ms）',
    problemPanelFieldMemoryLimit: '内存限制（MB）',
    problemPanelStatementPlaceholder: '在这里粘贴完整题面...',
    problemPanelFieldConstraintsNotes: '约束 / 备注',
    problemPanelConstraintsPlaceholder: '可选：列出数值范围、边界条件或希望智能体重点关注的备注。',
    problemPanelPublicTests: '公开测试',
    problemPanelPublicTestsHint: '添加希望智能体作为可信起始测试使用的样例。',
    problemPanelAddTest: '+ 添加测试',
    problemPanelSampleNumber: '样例 {number}',
    problemPanelRemove: '移除',
    problemPanelSaveCustomBeforeSolving: '保存到本地题库后再求解',
    problemPanelCustomMeta: '{chars} 个字符 • {tests} 个测试用例',
    problemPanelCodeforcesImport: 'Codeforces 导入',
    problemPanelCodeforcesHint: '按比赛/题号或标题搜索，然后将选中题目导入本地题库并求解。',
    problemPanelSearchCodeforces: '搜索 Codeforces',
    problemPanelSearching: '搜索中...',
    problemPanelSearch: '搜索',
    problemPanelCodeforcesResults: 'Codeforces 结果',
    problemPanelRatingPrefix: '评分',
    problemPanelImporting: '导入中...',
    problemPanelImportAndSolve: '导入并求解',
    problemPanelSearchCodeforcesEmpty: '搜索 Codeforces 以导入题目。',
    problemPanelNoSavedCustom: '还没有已保存的自定义题。',
    problemPanelLibraryActions: '题库操作',
    problemPanelRenameEdit: '重命名 / 编辑',
    problemPanelStarting: '启动中...',
    problemPanelSolveNow: '立即求解',
    problemPanelClone: '克隆',
    problemPanelExportJson: '导出 JSON',
    problemPanelSelectSavedCustom: '选择一个已保存自定义题进行编辑、求解或删除。',
    problemPanelMaxIterations: '最大迭代次数',
    problemPanelUpdateStartSolve: '更新并开始求解',
    problemPanelSaveStartSolve: '保存并开始求解',
    problemPanelUntitledCustomProblem: '未命名自定义题',
    problemPanelCopySuffix: '副本',
    problemPanelLoadLibraryFailed: '加载题库失败',
    problemPanelLoadSelectedFailed: '加载选中题目失败',
    problemPanelLoadSavedFailed: '加载已保存题目失败',
    problemPanelCloneSavedFailed: '克隆已保存题目失败',
    problemPanelExportSavedFailed: '导出已保存题目失败',
    problemPanelLaunchSavedFailed: '启动已保存题目失败',
    problemPanelDeleteConfirm: '从本地题库删除这个已保存自定义题？',
    problemPanelDeleteSavedFailed: '删除已保存题目失败',
    problemPanelSearchCodeforcesFailed: '搜索 Codeforces 失败',
    problemPanelImportCodeforcesFailed: '导入 Codeforces 题目失败',
    problemPanelSaveCustomFailed: '保存自定义题失败',
    problemPanelImportedMissingProblem: '导入的 Codeforces 响应缺少题目内容',
    problemPanelSavedMissingProblem: '保存自定义题响应缺少题目内容',
    problemPanelSolveDidNotStart: '求解未启动，请重试。',
    problemPanelSolveLaunchFailed: '启动求解失败',
  },
} as const;

const STAGE_TEXT: Record<JourneyStageId, Record<DashboardLanguage, Pick<JourneyStageCard, 'title' | 'summary' | 'what'> & { why: string }>> = {
  read_problem: {
    en: {
      title: 'Read Problem',
      summary: 'Turn the statement into structured constraints and tags.',
      what: 'The agent compresses the natural-language statement into machine-usable objectives, constraints, and problem tags.',
      why: 'A clean abstraction makes later code generation and checking less brittle.',
    },
    zh: {
      title: '阅读题目',
      summary: '将题面转成结构化约束和标签。',
      what: '智能体把自然语言题面压缩成机器可用的目标、约束和题目标签。',
      why: '清晰抽象能降低后续代码生成和检查的不稳定性。',
    },
  },
  full_testgen: {
    en: {
      title: 'Full Testgen',
      summary: 'Expand coverage when risk is high or checks ask for more evidence.',
      what: 'The agent generates a wider battery of tests to pressure candidate solutions.',
      why: 'More coverage is useful when the problem looks risky or trust remains low.',
    },
    zh: {
      title: '完整测例生成',
      summary: '在风险较高或需要更多证据时扩展覆盖。',
      what: '智能体生成更广泛的测试集合，对候选解施压。',
      why: '当题目风险较高或可信度不足时，更多覆盖能提供更强证据。',
    },
  },
  codegen: {
    en: {
      title: 'Codegen',
      summary: 'Draft, compile, and run the current solver attempt.',
      what: 'This stage writes code, compiles it, runs it on available tests, and learns from failures.',
      why: 'The agent needs a concrete solver candidate before it can verify or attack it.',
    },
    zh: {
      title: '代码生成',
      summary: '编写、编译并运行当前求解尝试。',
      what: '该阶段编写代码、完成编译、运行可用测试，并从失败中学习。',
      why: '智能体需要一个具体候选解，之后才能验证或攻击它。',
    },
  },
  hack: {
    en: {
      title: 'Hack',
      summary: 'Try to break the accepted-looking solution with adversarial inputs.',
      what: 'The agent stress-tests the candidate by searching for hidden counterexamples.',
      why: 'Late-stage breaking is the last chance to catch bugs before declaring success.',
    },
    zh: {
      title: 'Hack 检验',
      summary: '用对抗输入尝试击破看似通过的解法。',
      what: '智能体通过搜索隐藏反例对候选解做压力测试。',
      why: '末段破坏测试是在宣布成功前捕获缺陷的最后机会。',
    },
  },
};

const STATUS_LABEL_KEYS: Record<JourneyStageStatus, MessageKey> = {
  waiting: 'later',
  active: 'now',
  completed: 'done',
  skipped: 'skipped',
  repairing: 'repairing',
  failed: 'failed',
};

const DEFAULT_I18N: DashboardI18nContextValue = {
  language: 'en',
  setLanguage: () => {},
  toggleLanguage: () => {},
  t: (key) => MESSAGES.en[key],
};

const DashboardI18nContext = createContext<DashboardI18nContextValue>(DEFAULT_I18N);

export function DashboardI18nProvider({ children }: { children: ReactNode }) {
  const [language, setLanguage] = useState<DashboardLanguage>('en');
  const value = useMemo<DashboardI18nContextValue>(() => ({
    language,
    setLanguage,
    toggleLanguage: () => setLanguage((current) => (current === 'en' ? 'zh' : 'en')),
    t: (key) => MESSAGES[language][key],
  }), [language]);

  return <DashboardI18nContext.Provider value={value}>{children}</DashboardI18nContext.Provider>;
}

export function useI18n(): DashboardI18nContextValue {
  return useContext(DashboardI18nContext);
}

export function stageText(language: DashboardLanguage, stageId: JourneyStageId) {
  return STAGE_TEXT[stageId][language];
}

export function stageStatusLabel(language: DashboardLanguage, status: JourneyStageStatus): string {
  return MESSAGES[language][STATUS_LABEL_KEYS[status]];
}

export function formatStageVisits(language: DashboardLanguage, visits: number): string {
  if (visits <= 0) return MESSAGES[language].notVisitedYet;
  if (language === 'zh') return `${visits} 次访问`;
  return `${visits} pass${visits > 1 ? 'es' : ''}`;
}

export function localizeStageCard(language: DashboardLanguage, stage: JourneyStageCard): JourneyStageCard {
  const text = stageText(language, stage.id);
  return {
    ...stage,
    title: text.title,
    summary: localizeDashboardText(language, stage.summary) || text.summary,
    what: text.what,
    evidence: stage.evidence.map((line) => localizeDashboardText(language, line)),
    whyNotes: stage.whyNotes.map((line) => localizeDashboardText(language, line)),
    steps: stage.steps.map((step) => localizeJourneyStep(language, step)),
  };
}

const FAMILY_LABELS: Record<AlgorithmVisualization['family'], Record<DashboardLanguage, string>> = {
  bfs: { en: 'BFS', zh: '广度优先搜索' },
  dfs_recursion: { en: 'DFS / Recursion', zh: '深度优先搜索 / 递归' },
  basic_dp: { en: 'Basic DP', zh: '基础动态规划' },
  two_pointers: { en: 'Two Pointers', zh: '双指针' },
  sliding_window: { en: 'Sliding Window', zh: '滑动窗口' },
  binary_search: { en: 'Binary Search', zh: '二分搜索' },
  prefix_sum: { en: 'Prefix Sum', zh: '前缀和' },
  union_find: { en: 'Union Find', zh: '并查集' },
  topological_sort: { en: 'Topological Sort', zh: '拓扑排序' },
  greedy_interval: { en: 'Greedy Interval', zh: '区间贪心' },
  monotonic_stack: { en: 'Monotonic Stack', zh: '单调栈' },
  unsupported: { en: 'Unsupported', zh: '暂不支持' },
};

const EXACT_TEXT_ZH: Record<string, string> = {
  'Abstracting Problem': '题目抽象',
  'Generating Tests': '生成测试',
  'Planning Strategy': '规划策略',
  'Generating & Testing Code': '生成并测试代码',
  'Draft, compile, and run the current solver attempt.': '编写、编译并运行当前求解尝试。',
  idle: '空闲',
  live: '实时',
  replay: '回放',
  connected: '已连接',
  connecting: '连接中',
  reconnecting: '重连中',
  disconnected: '已断开',
  ready: '已就绪',
  missing: '缺失',
  error: '错误',
  success: '成功',
  accepted: '已接受',
  cancelled: '已取消',
  max_iterations: '达到迭代上限',
  terminal_failure: '终止失败',
  SAFE: '安全',
  REPAIR: '需修复',
  repair: '需修复',
  'not used': '未使用',
  code: '代码',
  tests: '测试',
  result: '结果',
  counterexample: '反例',
  'Replay Progress': '回放进度',
  'Scrub the run by stage or exact event position': '按阶段或精确事件位置拖动回放',
  'The map, timeline, and live progress panels stay synced to the replay cursor.': '地图、时间线和实时进度面板会与回放游标保持同步。',
  'Evidence Workbench': '证据工作台',
  'Code, tests, result, and counterexamples in one place': '集中查看代码、测试、结果和反例',
  version: '版本',
  lines: '行',
  'emitted solution': '生成的解法',
  'diff vs': '对比',
  'Code diff': '代码差异',
  old: '旧',
  'new': '新',
  'Public / trusted tests': '公开 / 可信测试',
  sample: '样例',
  'No public tests were provided.': '没有提供公开测试。',
  'Generated / carried tests': '生成 / 继承测试',
  generated: '生成测试',
  trusted: '可信',
  advisory: '参考',
  'No generated test snapshot is available yet.': '暂无生成测试快照。',
  'No emitted solution snapshot is available yet for this run.': '本次运行暂无生成解法快照。',
  'Final result': '最终结果',
  'not reached': '尚未到达',
  'visible tests': '可见测试',
  'full testgen': '完整测例生成',
  done: '完成',
  skipped: '已跳过',
  'No final feedback summary was emitted.': '未输出最终反馈总结。',
  'Failure Analysis': '失败分析',
  'needs repair': '需要修复',
  'Likely root cause': '可能根因',
  'Failure chain': '失败链路',
  'Structured signals': '结构化信号',
  'Compilation errors': '编译错误',
  'Suggested fixes': '建议修复',
  'Hack failures': 'Hack 失败',
  'Runtime errors': '运行时错误',
  'Execution log tail': '执行日志尾部',
  'Read Problem': '阅读题目',
  'Full Testgen': '完整测例生成',
  Codegen: '代码生成',
  'Run Ended': '运行结束',
  System: '系统',
  'Repair budget exhausted': '修复预算已耗尽',
  'Terminal failure after hack': 'Hack 后终止失败',
  'Workflow runtime error': '工作流运行时错误',
  'The solver ran out of repair budget.': '求解器耗尽修复预算。',
  'The run kept looping through codegen and repair, but never reached an accepted solution before the iteration budget ran out.': '本次运行持续在代码生成和修复间循环，但在迭代预算耗尽前未达到可接受解法。',
  'The workflow kept repairing the candidate, but never gathered enough evidence to accept it before the iteration budget ran out.': '工作流持续修复候选解，但在迭代预算耗尽前始终没有收集到足够证据来接受它。',
  'The workflow hit the iteration cap before it could produce an accepted solution.': '工作流在生成可接受解法前触达迭代上限。',
  'The workflow crashed before a final result.': '工作流在生成最终结果前崩溃。',
  'A runtime-level error interrupted the solve loop, so the run ended without a clean final decision.': '运行时级别错误中断了求解循环，因此本次运行没有得到干净的最终决策。',
  'A hack-stage counterexample broke the candidate.': 'Hack 阶段反例击破了候选解。',
  'The candidate looked acceptable until adversarial testing produced a concrete breaking input.': '候选解看似可接受，但对抗测试生成了具体破坏性输入。',
  'The current attempt is failing and being repaired.': '当前尝试失败，正在修复。',
  'Compilation failed on the current draft, and the agent is analyzing how to patch the code.': '当前草稿编译失败，智能体正在分析如何修补代码。',
  'The hacker found a live counterexample.': 'Hack 检验发现了实时反例。',
  'Adversarial testing produced a breaking input that sent the solver back into repair.': '对抗测试生成了破坏性输入，并将求解器送回修复。',
  'Hack generation is blocked right now.': '当前 Hack 生成受阻。',
  'The hack pipeline could not produce a valid adversarial candidate on this pass.': '本轮 Hack 流程未能生成有效对抗候选。',
  'The run ended without an accepted solution.': '本次运行结束，但没有得到可接受解法。',
  'A late-stage adversarial counterexample broke the candidate and the workflow stopped.': '后期对抗反例击破候选解，工作流已停止。',
  'A final adversarial test exposed a bug that the workflow could not repair in time.': '最终对抗测试暴露了一个工作流未能及时修复的缺陷。',
  'The workflow stopped without producing a trustworthy accepted solution.': '工作流停止时尚未生成可信的可接受解法。',
  'Add the missing semicolon.': '补上缺失的分号。',
  'Declare the missing variable before use.': '在使用前声明缺失变量。',
  'failure case recorded': '已记录失败用例',
  'Risk flags / log tail': '风险标记 / 日志尾部',
  'Hack counterexamples': 'Hack 反例',
  'hack failure': 'Hack 失败',
  expected: '期望',
  actual: '实际',
  'No adversarial break case is stored for this run.': '本次运行未保存对抗破坏用例。',
  'Turn the statement into structured constraints and tags.': '将题面转成结构化约束和标签。',
  'Expand coverage when risk is high or checks ask for more evidence.': '在风险较高或需要更多证据时扩展覆盖。',
  'Adversarial Hack Testing': '对抗 Hack 检验',
  'Try to break the solution': '尝试击破解法',
  'Trying to generate a breaking input.': '正在生成破坏性输入。',
  'Record hack lessons': '记录 Hack 经验',
  'Recording what the hacker learned.': '正在记录 Hack 检验获得的经验。',
  'Hack 检验': 'Hack 检验',
  'Read the statement': '阅读题面',
  'Generate more tests': '生成更多测试',
  'Choose a strategy': '选择策略',
  'Compare strategy branches': '比较策略分支',
  'Draft solver code': '起草求解代码',
  'Compile the draft': '编译草稿',
  'Prepare artifacts': '准备运行产物',
  'Run available tests': '运行可用测试',
  'Keep the best candidate': '保留最佳候选解',
  'Score the attempt': '评估本次尝试',
  'Store planning lessons': '存储规划经验',
  'Store solving lessons': '存储求解经验',
  'Store oracle hints': '存储判题提示',
  'Analyze failures': '分析失败原因',
  'Restore best solution': '恢复最佳解',
  'Promote to hack mode': '进入 Hack 模式',
  'Extracting objective, constraints, and hidden structure.': '正在提取目标、约束和隐藏结构。',
  'Expanding coverage with broader generated examples.': '正在用更广的生成样例扩展覆盖。',
  'Choosing an algorithmic direction before coding.': '编码前正在选择算法方向。',
  'Comparing multiple strategy branches before choosing one.': '正在比较多个策略分支后再选择。',
  'Writing the current solver draft.': '正在编写当前求解器草稿。',
  'Checking that the latest draft builds cleanly.': '正在检查最新草稿能否干净编译。',
  'Preparing the compiled solver for execution.': '正在准备已编译求解器以便执行。',
  'Running the current draft against the available suite.': '正在用可用测试集运行当前草稿。',
  'Keeping the strongest candidate seen so far.': '正在保留目前最强候选解。',
  'Summarizing how well the current attempt performed.': '正在总结当前尝试表现。',
  'Saving planning lessons for future retries.': '正在保存规划经验供后续重试使用。',
  'Saving solution lessons from this attempt.': '正在保存本次求解经验。',
  'Saving feedback for future reasoning.': '正在保存反馈供后续推理使用。',
  'Turning failed tests into concrete repair hints.': '正在把失败测试转成具体修复提示。',
  'Restoring the best-known candidate before stopping.': '停止前正在恢复已知最佳候选解。',
  'Moving the candidate into adversarial stress testing.': '正在将候选解送入对抗压力测试。',
  'Processing this step.': '正在处理该步骤。',
  'Using a planner to choose a stronger strategy before coding.': '编码前使用规划器选择更稳的策略。',
  'Locked in a strategy and prepared to write the solver.': '已确定策略，准备编写求解器。',
  'Converted the statement into a structured internal problem model.': '已将题面转成结构化内部问题模型。',
  'Finished widening the test suite.': '已完成测试集扩展。',
  'The planner ran before coding to reduce blind trial-and-error.': '编码前先运行规划器，以减少盲目试错。',
  'This stage was revisited because earlier evidence was still not strong enough.': '由于先前证据仍不够强，本阶段被重新访问。',
  'A previous codegen or hack result sent the agent back for repair.': '先前代码生成或 Hack 结果将智能体送回修复。',
  'The hacker found a concrete counterexample, so the solver must repair against it.': 'Hack 检验发现了具体反例，求解器必须据此修复。',
  'Late-stage breaking is the last chance to catch bugs before declaring success.': '末段破坏测试是在宣布成功前捕获缺陷的最后机会。',
  'Try to break the accepted-looking solution with adversarial inputs.': '用对抗输入尝试击破看似通过的解法。',
  'Next: either declare the solver safe or send a breaking input back for repair.': '下一步：确认解法安全，或把破坏性输入送回修复。',
  'Next: generate stronger tests and move into code generation.': '下一步：生成更强测试并进入代码生成。',
  'Next: move into code generation with a stronger test bed.': '下一步：带着更强测试集进入代码生成。',
  'Next: iterate on the draft and then move into adversarial hacking if it passes.': '下一步：迭代草稿；若通过则进入对抗 Hack。',
  'Replay any stage below to inspect how the agent arrived here.': '回放下方任一阶段，查看智能体如何到达这里。',
  'Inspect the latest codegen and hack passes to see where progress stalled.': '查看最新代码生成和 Hack 访问，定位进展停滞处。',
  'Focus on the final hack rounds and the repair loop that followed them.': '重点查看最终 Hack 轮次及随后的修复循环。',
  'Use the timeline below to inspect the decision path.': '使用下方时间线检查决策路径。',
  'Pick a problem to watch the solve journey.': '选择一道题来观看求解旅程。',
  'The dashboard is ready for a live run or a replay of a previous solve.': 'Dashboard 已准备好进行实时运行或回放历史求解。',
  'Next: start a solve from the header or open a replay from the run list.': '下一步：从顶部开始求解，或从运行列表打开回放。',
  'The solver survived visible tests and adversarial breaking.': '求解器通过了可见测试并经受住对抗破坏。',
  'The current candidate was accepted.': '当前候选解已被接受。',
  'The solver ran out of repair budget before it became trustworthy.': '求解器在变得可信前耗尽了修复预算。',
  'A late-stage hack found a break the solver could not recover from.': '后期 Hack 找到了求解器无法恢复的问题。',
  'The workflow reached a final state.': '工作流已到达最终状态。',
  'The workflow has reached a final outcome.': '工作流已到达最终结果。',
  'Run complete': '运行完成',
  'Waiting for next event': '等待下一个事件',
  'Preparing progress view.': '正在准备进度视图。',
  'This run does not yet support animated algorithm playback.': '本次运行暂不支持算法动画回放。',
  'Executable not ready yet, so this trace is not code-validated.': '可执行文件尚未准备好，因此这条轨迹未经过代码验证。',
  'Executable is unavailable, so this trace is not code-validated.': '可执行文件不可用，因此这条轨迹未经过代码验证。',
  'The emitted solution matches the sample output on this trace.': '该解法在这条轨迹上输出与样例输出一致。',
  'The emitted solution failed while running on the sample input.': '该解法在样例输入上运行失败。',
  'The emitted solution output does not match the sample output for this trace.': '该解法在这条轨迹上的输出与样例输出不一致。',
  'Breadth-first search walkthrough': '广度优先搜索过程演示',
  'BFS Execution Trace': 'BFS 执行轨迹',
  'BFS Code Trace': 'BFS 代码轨迹',
  'Binary Search Execution Trace': '二分搜索执行轨迹',
  'Binary Search Code Trace': '二分搜索代码轨迹',
  'Two-Pointer Execution Trace': '双指针执行轨迹',
  'Two-Pointer Code Trace': '双指针代码轨迹',
  'Sliding Window Execution Trace': '滑动窗口执行轨迹',
  'Sliding Window Code Trace': '滑动窗口代码轨迹',
  'Prefix Sum Execution Trace': '前缀和执行轨迹',
  'Prefix Sum Code Trace': '前缀和代码轨迹',
  'Grid DP Execution Trace': '网格 DP 执行轨迹',
  'Grid DP Code Trace': '网格 DP 代码轨迹',
  'Union-Find Execution Trace': '并查集执行轨迹',
  'Union-Find Code Trace': '并查集代码轨迹',
  'Topological Sort Execution Trace': '拓扑排序执行轨迹',
  'Topological Sort Code Trace': '拓扑排序代码轨迹',
  'Greedy Interval Execution Trace': '区间贪心执行轨迹',
  'Greedy Interval Code Trace': '区间贪心代码轨迹',
  'Monotonic Stack Execution Trace': '单调栈执行轨迹',
  'Monotonic Stack Code Trace': '单调栈代码轨迹',
  'DFS Recursion Execution Trace': 'DFS 递归执行轨迹',
  'DFS Result Code Trace': 'DFS 结果代码轨迹',
  'Trace the queue while BFS visits the graph.': '跟踪 BFS 访问图时队列的变化。',
  'A sample-driven trace of queue expansion and shortest-distance discovery.': '基于样例展示队列扩展和最短距离发现过程。',
  'A variable-level trace captured from the emitted C++ BFS implementation.': '从生成的 C++ BFS 实现中捕获的变量级轨迹。',
  'A sample-driven trace of how binary search shrinks the search interval.': '基于样例展示二分搜索如何收缩搜索区间。',
  'A variable-level trace captured from the emitted C++ binary search implementation.': '从生成的 C++ 二分搜索实现中捕获的变量级轨迹。',
  'A sample-driven trace of the left and right pointers moving toward a target sum.': '基于样例展示左右指针如何逼近目标和。',
  'A variable-level trace captured from the emitted C++ two-pointer implementation.': '从生成的 C++ 双指针实现中捕获的变量级轨迹。',
  'A sample-driven trace of window expansion and shrinking on the public test.': '基于公开测试展示窗口扩展和收缩过程。',
  'A variable-level trace captured from the emitted C++ sliding-window implementation.': '从生成的 C++ 滑动窗口实现中捕获的变量级轨迹。',
  'A sample-driven trace of cumulative sums and the final range query formula.': '基于样例展示前缀和累计与最终区间查询公式。',
  'A variable-level trace captured from the emitted C++ prefix-sum implementation.': '从生成的 C++ 前缀和实现中捕获的变量级轨迹。',
  'A sample-driven trace of how the DP table is filled cell by cell.': '基于样例展示 DP 表如何逐格填充。',
  'A variable-level trace captured from the emitted C++ dynamic-programming implementation.': '从生成的 C++ 动态规划实现中捕获的变量级轨迹。',
  'A sample-driven trace of how connected components merge after each edge.': '基于样例展示每条边后连通分量如何合并。',
  'A variable-level trace captured from the emitted C++ union-find implementation.': '从生成的 C++ 并查集实现中捕获的变量级轨迹。',
  "A sample-driven trace of Kahn's algorithm on the public DAG.": '基于公开 DAG 展示 Kahn 拓扑排序过程。',
  'A variable-level trace captured from the emitted C++ topological-sort implementation.': '从生成的 C++ 拓扑排序实现中捕获的变量级轨迹。',
  'A sample-driven trace of interval scheduling by earliest finishing time.': '基于样例展示按最早结束时间进行区间调度。',
  'A variable-level trace captured from the emitted greedy interval-scheduling implementation.': '从生成的区间贪心实现中捕获的变量级轨迹。',
  'A sample-driven trace of next-greater-element processing from right to left.': '基于样例展示从右到左处理下一个更大元素。',
  'A variable-level trace captured from the emitted monotonic-stack implementation.': '从生成的单调栈实现中捕获的变量级轨迹。',
  'A sample-driven trace of recursive subtree-size computation.': '基于样例展示递归计算子树大小的过程。',
  'A code-aware trace derived from the emitted DFS/subtree-size solution.': '从生成的 DFS/子树大小解法推导出的代码感知轨迹。',
  'public sample': '公开样例',
  'first sample': '第一个样例',
  public_test_1: '公开测试 1',
  'execution-trace': '执行轨迹',
  'code-instrumented': '代码插桩',
  teaching: '教学模式',
  showcase: '示例模式',
  'Build the graph': '构建图',
  'Construct adjacency lists from the sample edges.': '根据样例边构建邻接表。',
  'The emitted solution builds adjacency lists from the sample edges.': '该解法会根据样例边构建邻接表。',
  'Start at node 1': '从节点 1 开始',
  'Initialize the queue with the starting node.': '用起始节点初始化队列。',
  'Mark the source visited and push it into the queue.': '标记源点已访问，并将其推入队列。',
  'The emitted solution initializes the BFS queue from node 1.': '该解法会从节点 1 初始化 BFS 队列。',
  'Visit each unvisited neighbor and record its shortest distance.': '访问每个未访问邻居，并记录其最短距离。',
  'This discovered neighbor was captured from the emitted solution.': '这个新发现的邻居来自已生成解法的运行轨迹。',
  'Reach the target': '到达目标',
  'Read the shortest-path length printed by the emitted solution.': '读取生成解法输出的最短路径长度。',
  'The first time node n is discovered, its BFS distance is optimal.': '节点 n 第一次被发现时，其 BFS 距离就是最优距离。',
  'Initialize search range': '初始化搜索范围',
  'Start with the full sorted array.': '从完整有序数组开始。',
  'Start from the full range used by the emitted solution.': '从生成解法使用的完整范围开始。',
  'Check middle element': '检查中间元素',
  'The target is found at mid.': '目标在 mid 处找到。',
  'Discard the left half including mid.': '丢弃包含 mid 的左半部分。',
  'Discard the right half including mid.': '丢弃包含 mid 的右半部分。',
  'Narrow to right half': '缩小到右半区间',
  'Narrow to left half': '缩小到左半区间',
  'Continue searching in the remaining right interval.': '继续在剩余右区间搜索。',
  'Continue searching in the remaining left interval.': '继续在剩余左区间搜索。',
  'Return answer': '返回答案',
  'Return answers': '返回答案数组',
  'Binary search stops at the matching index.': '二分搜索在匹配下标处停止。',
  'Read the final answer printed by the emitted solution.': '读取生成解法打印的最终答案。',
  'These values come from the instrumented emitted solution, not a simulator.': '这些值来自插桩后的生成解法，而不是模拟器。',
  'Initialize pointers': '初始化指针',
  'Start from both ends of the sorted array.': '从有序数组两端开始。',
  'Start from both ends exactly as the emitted solution does.': '按照生成解法的方式从两端开始。',
  'Check pair sum': '检查指针对和',
  'This pair hits the target exactly.': '这对数正好命中目标。',
  'The sum is too small, so move the left pointer.': '当前和太小，因此移动左指针。',
  'The sum is too large, so move the right pointer.': '当前和太大，因此移动右指针。',
  'The two-pointer sweep finishes.': '双指针扫描结束。',
  'These pointer values were captured from the instrumented emitted solution.': '这些指针值来自插桩后的生成解法。',
  'Initialize window': '初始化窗口',
  'Start with an empty window and expand to the right.': '从空窗口开始并向右扩展。',
  'Start with the same empty window state as the emitted solution.': '从与生成解法相同的空窗口状态开始。',
  'Expand window': '扩展窗口',
  'Shrink window': '收缩窗口',
  'Update best length': '更新最佳长度',
  'These window boundaries come from the instrumented emitted solution.': '这些窗口边界来自插桩后的生成解法。',
  'Valid window found': '找到合法窗口',
  'The current window already reaches the target sum.': '当前窗口已经达到目标和。',
  'Shrink from the left': '从左侧收缩',
  'Try to shorten the window while keeping it valid.': '在保持合法的同时尝试缩短窗口。',
  'Take the minimum length found across all valid windows.': '取所有合法窗口中的最小长度。',
  'Read sample input': '读取样例输入',
  'Load the array and the query range.': '载入数组和查询区间。',
  'The emitted solution starts with the raw array and query bounds.': '生成解法从原始数组和查询边界开始。',
  'Initialize prefix sums': '初始化前缀和',
  'prefix[0] = 0 makes one-indexed range formulas easy.': 'prefix[0] = 0 让一基区间公式更简单。',
  'The emitted solution starts with prefix[0] = 0.': '生成解法从 prefix[0] = 0 开始。',
  'Extend prefix array': '扩展前缀数组',
  'Append the next cumulative total.': '追加下一个累计和。',
  'Apply range formula': '应用区间公式',
  'Subtract the prefix before l from the prefix at r.': '用 r 处前缀减去 l 前一个位置的前缀。',
  'Use the emitted prefix array to answer the sample query.': '使用生成的前缀数组回答样例查询。',
  'The range sum comes directly from the prefix array.': '区间和直接来自前缀数组。',
  'Read the grid': '读取网格',
  'The DP table will mirror the sample grid.': 'DP 表会对应样例网格。',
  'The emitted solution allocates a DP table for the sample grid.': '生成解法为样例网格分配 DP 表。',
  'Start at the first cell': '从第一个单元格开始',
  'The base case is the value in the top-left corner.': '基础状态是左上角的值。',
  'Combine the best incoming path with the current grid value.': '将最佳前驱路径与当前网格值合并。',
  'The bottom-right DP value is the answer on the sample.': '右下角 DP 值就是样例答案。',
  'This DP value was captured from the emitted solution.': '这个 DP 值来自生成解法。',
  'Initialize the base case at the top-left corner.': '初始化左上角基础状态。',
  'Initialize sets': '初始化集合',
  'Each node begins in its own singleton component.': '每个节点一开始都是单点连通分量。',
  'The emitted solution starts with one component per node.': '生成解法从每个节点一个分量开始。',
  'Union the components touched by the new edge.': '合并新边连接到的连通分量。',
  'This successful union was captured from the emitted solution.': '这次成功合并来自生成解法。',
  'Final answer': '最终答案',
  'Count the remaining disjoint sets after all unions.': '统计所有合并后的剩余不交集合数。',
  'Read the remaining component count printed by the emitted solution.': '读取生成解法打印的剩余连通分量数。',
  'Build indegrees': '构建入度',
  'Count incoming edges and enqueue every zero-indegree node.': '统计入边，并将所有零入度节点入队。',
  'The emitted solution computes indegrees and seeds the zero-indegree queue.': '生成解法计算入度并初始化零入度队列。',
  'Remove one zero-indegree node and decrease the indegrees of its outgoing neighbors.': '移除一个零入度节点，并降低其出边邻居的入度。',
  'This pop order was captured from the emitted solution; queue evolution is reconstructed from the sample DAG.': '弹出顺序来自生成解法；队列演化由样例 DAG 重建。',
  'Read the final topological ordering printed by the emitted solution.': '读取生成解法打印的最终拓扑序。',
  'Read intervals': '读取区间',
  'Load every interval from the sample input.': '从样例输入载入所有区间。',
  'Sort by end time': '按结束时间排序',
  'Greedy interval scheduling starts by sorting on finishing times.': '区间贪心调度从按结束时间排序开始。',
  'The emitted solution sorts intervals before sweeping greedily.': '生成解法先排序区间，再贪心扫描。',
  'Keep the interval only if it does not overlap with the last accepted one.': '只有当区间不与上一个已接受区间重叠时才保留。',
  'This accepted interval was captured from the emitted solution.': '这个被接受的区间来自生成解法。',
  'The greedy count is optimal when intervals are processed by end time.': '按结束时间处理区间时，贪心计数是最优的。',
  'Read the maximum number of non-overlapping intervals printed by the emitted solution.': '读取生成解法打印的最大不重叠区间数。',
  'Pop smaller values, record the next greater element, then push the current value.': '弹出较小值，记录下一个更大元素，再压入当前值。',
  'This next-greater assignment was captured from the emitted solution.': '这个下一个更大元素赋值来自生成解法。',
  'Every position now knows its next greater element to the right.': '现在每个位置都知道其右侧下一个更大元素。',
  'Read the final next-greater array printed by the emitted solution.': '读取生成解法打印的最终下一个更大元素数组。',
  'Read the tree': '读取树',
  'Build an undirected adjacency list from the sample edges.': '根据样例边构建无向邻接表。',
  'The emitted solution only needs to consume the edges from input.': '生成解法只需要读取输入中的边。',
  'Push the current node onto the recursion stack.': '将当前节点压入递归栈。',
  'All children are done, so return the accumulated subtree size.': '所有子节点已处理完，返回累计子树大小。',
  'The subtree size at the root is the final answer on the sample.': '根节点的子树大小就是样例最终答案。',
  'Read the subtree size printed by the emitted solution.': '读取生成解法打印的子树大小。',
  Queue: '队列',
  target: '目标',
  neighbors: '邻居',
  empty: '空',
  none: '无',
  'none yet': '暂无',
  'not started': '尚未开始',
  'not selected': '未选择',
  'not evaluated yet': '尚未评估',
  'not specified': '未指定',
  returning: '正在返回',
  'Visited / New': '已访问 / 新发现',
  'Current Focus': '当前焦点',
  'No DP table emitted for this step.': '该步骤未输出 DP 表。',
  'Current Transition': '当前转移',
  'Current Best Answer': '当前最佳答案',
  'Input View': '输入视图',
  'still filling the table': '仍在填表',
  Pointers: '指针',
  left: '左指针',
  right: '右指针',
  sum: '和',
  'vs target': '对比目标',
  'left value': '左值',
  'right value': '右值',
  answer: '答案',
  'Current Check': '当前检查',
  Bounds: '边界',
  low: '低位',
  high: '高位',
  value: '值',
  next: '下一段',
  'result index': '结果下标',
  'Target Check': '目标检查',
  'Call Stack': '调用栈',
  'Current Call': '当前调用',
  'Returned Values': '返回值',
  'No recursion tree emitted for this step.': '该步骤未输出递归树。',
  'stack empty': '调用栈为空',
  Window: '窗口',
  'Current State': '当前状态',
  'Window Elements': '窗口元素',
  'best length': '最佳长度',
  'final answer': '最终答案',
  'empty window': '空窗口',
  'window not evaluated yet': '窗口尚未评估',
  'Running Total': '运行总和',
  'Query / Use': '查询 / 使用',
  'Range Answer': '区间答案',
  'building prefix values': '正在构建前缀值',
  'not answered yet': '尚未作答',
  'Current Union': '当前合并',
  Components: '连通分量',
  component: '分量',
  Progress: '进度',
  'processed edges': '已处理边数',
  'no components emitted': '未输出连通分量',
  'Zero-indegree queue': '零入度队列',
  'Processed order': '已处理顺序',
  'Current Node': '当前节点',
  'next available': '下一批可用节点',
  'no unlocked node remains': '没有剩余已解锁节点',
  'Current interval': '当前区间',
  'Last chosen end': '上个已选结束点',
  Decision: '决策',
  'chosen count': '已选择数量',
  kept: '保留',
  candidate: '候选',
  'Monotonic Stack': '单调栈',
  'Current Index': '当前下标',
  Action: '动作',
  'Popped / Answer': '弹出值 / 答案',
  pop: '弹出',
  ans: '答案',
  'empty stack': '空栈',
  'no action yet': '暂无动作',
  'nothing popped': '未弹出元素',
};

const STATUS_TEXT_ZH: Record<string, string> = {
  Idle: '空闲',
  Running: '运行中',
  Repairing: '修复中',
  Hacking: 'Hack 中',
  Accepted: '已接受',
  Stopped: '已停止',
  Failed: '失败',
  Finished: '已结束',
  active: '进行中',
  completed: '完成',
  repairing: '修复中',
  failed: '失败',
  skipped: '已跳过',
};

function localizeStrategyText(text: string): string {
  const trimmed = text.trim();
  if (trimmed === 'P: Iterate through the array once while maintaining a hash map from previously seen value to its index.') {
    return 'P：单次遍历数组，同时维护从已见数值到其下标的哈希表。';
  }
  return trimmed.replace(/^P:\s*/, 'P：');
}

function replaceKnownEnglish(text: string): string {
  let output = EXACT_TEXT_ZH[text] || text;
  output = output.replace(/^Now in Hack(?:, pass (\d+))?$/, (_match, pass) => (
    pass ? `当前在 Hack 检验，第 ${pass} 次访问` : '当前在 Hack 检验'
  ));
  output = output.replace(/^Now in Full Testgen(?:, pass (\d+))?$/, (_match, pass) => (
    pass ? `当前在完整测例生成，第 ${pass} 次访问` : '当前在完整测例生成'
  ));
  output = output.replace(/^Now in Codegen(?:, pass (\d+))?$/, (_match, pass) => (
    pass ? `当前在代码生成，第 ${pass} 次访问` : '当前在代码生成'
  ));
  output = output.replace(/^Hack round (\d+) did not find a breaking input\.$/, '第 $1 轮 Hack 未找到破坏性输入。');
  output = output.replace(/^Hack round (\d+) found a breaking case and sent the solver back for repair\.$/, '第 $1 轮 Hack 找到破坏性用例，并将求解器送回修复。');
  output = output.replace(/^Hack round (\d+) completed\.$/, '第 $1 轮 Hack 已完成。');
  output = output.replace(/^Hack round (\d+) target passed\. Pending reward settlement\.$/, '第 $1 轮 Hack 目标通过，等待奖励结算。');
  output = output.replace(/^Hack FAILED \(Found (\d+) bugs\)\. Pending reward settlement\.$/, 'Hack 失败（发现 $1 个缺陷），等待奖励结算。');
  output = output.replace(/^Hack round: (\d+)$/, 'Hack 轮次：$1');
  output = output.replace(/^(.+) memory: no items to settle$/, '$1 记忆：暂无可结算条目');
  output = output.replace(/^(.+) memory: no items to update$/, '$1 记忆：暂无可更新条目');
  output = output.replace(/^Failure type: (.+)$/, '失败类型：$1');
  output = output.replace(/^iterations: (.+)$/, '迭代次数：$1');
  output = output.replace(/^visible pass rate: (.+)$/, '可见通过率：$1');
  output = output.replace(/^hack result: (.+)$/, 'Hack 结果：$1');
  output = output.replace(/^hack round: (.+)$/, 'Hack 轮次：$1');
  output = output.replace(/^type: /, '类型：');
  output = output.replace(/expected (.+?) \/ actual (.+)$/, '期望 $1 / 实际 $2');
  output = output.replace(/^Workflow execution failed: (.+)$/, '工作流执行失败：$1');
  output = output.replace(/^Input head: (.+)$/, '输入片段：$1');
  output = output.replace(/^Expected head: (.+)$/, '期望输出片段：$1');
  output = output.replace(/^Actual head: (.+)$/, '实际输出片段：$1');
  output = output.replace(/^Details: (.+)$/, '详情：$1');
  output = output.replace(/^Visible test score: (\d+)\/(\d+) \((\d+)%\)\.$/, '可见测试得分：$1/$2（$3%）。');
  output = output.replace(/^Latest visible score: (\d+)\/(\d+)\.$/, '最新可见测试得分：$1/$2。');
  output = output.replace(/^Attempt (\d+) passed (\d+) of (\d+) tests \((\d+)%\)\.$/, '第 $1 次尝试通过 $2/$3 个测试（$4%）。');
  output = output.replace(/^Attempt (\d+) failed to compile cleanly and needs repair\.$/, '第 $1 次尝试未能干净编译，需要修复。');
  output = output.replace(/^Finished codegen attempt (\d+)\.$/, '完成第 $1 次代码生成尝试。');
  output = output.replace(/^Generated (\d+) broader tests before trusting the solver\.$/, '在信任求解器前生成了 $1 个更广覆盖的测试。');
  output = output.replace(/^Expanded coverage with (\d+) newly generated tests after additional risk was detected\.$/, '检测到额外风险后，新增 $1 个生成测试来扩展覆盖。');
  output = output.replace(/^Mapped the problem around (.+)\.$/, '已围绕 $1 映射题目。');
  output = output.replace(/^Mapped the problem to (.+) with (\d+)% abstraction confidence\.$/, '已将题目映射为 $1，抽象置信度 $2%。');
  output = output.replace(/^Tags: (.+)$/, '标签：$1');
  output = output.replace(/^Generated tests: (\d+)$/, '生成测试数：$1');
  output = output.replace(/^Planned strategy: (.+)$/, (_match, strategy) => `规划策略：${localizeStrategyText(strategy)}`);
  output = output.replace(/^Compile status: success$/, '编译状态：成功');
  output = output.replace(/^Compile status: failure$/, '编译状态：失败');
  output = output.replace(/^Visible tests: (\d+)\/(\d+)$/, '可见测试：$1/$2');
  output = output.replace(/^Pass rate: (\d+)%$/, '通过率：$1%');
  output = output.replace(/^Attempt: (\d+)$/, '尝试：$1');
  output = output.replace(/^Step (\d+)$/, '步骤 $1');
  output = output.replace(/^Start BFS at node (.+)$/, '从节点 $1 开始 BFS');
  output = output.replace(/^Start at node (.+)$/, '从节点 $1 开始');
  output = output.replace(/^Extend to index (.+)$/, '扩展到下标 $1');
  output = output.replace(/^Fill first row cell \((.+),(.+)\)$/, '填充第一行单元格（$1,$2）');
  output = output.replace(/^Fill first column cell \((.+),(.+)\)$/, '填充第一列单元格（$1,$2）');
  output = output.replace(/^Compute cell \((.+),(.+)\)$/, '计算单元格（$1,$2）');
  output = output.replace(/^Update dp\[(.+)\]\[(.+)\]$/, '更新 dp[$1][$2]');
  output = output.replace(/^Update prefix\[(.+)\]$/, '更新 prefix[$1]');
  output = output.replace(/^Accumulate a\[(.+)\]$/, '累加 a[$1]');
  output = output.replace(/^Process edge (.+)-(.+)$/, '处理边 $1-$2');
  output = output.replace(/^Take node (.+)$/, '取出节点 $1');
  output = output.replace(/^Take interval (.+)-(.+)$/, '选择区间 $1-$2');
  output = output.replace(/^Skip interval (.+)-(.+)$/, '跳过区间 $1-$2');
  output = output.replace(/^Process index (.+)$/, '处理下标 $1');
  output = output.replace(/^Enter dfs\((.+)\)$/, '进入 dfs($1)');
  output = output.replace(/^Return from dfs\((.+)\)$/, '从 dfs($1) 返回');
  output = output.replace(/^Load a graph with (\d+) nodes and (\d+) edges\.$/, '载入包含 $1 个节点、$2 条边的图。');
  output = output.replace(/^Initialize BFS from node (.+) with distance 0\.$/, '从节点 $1 初始化 BFS，距离为 0。');
  output = output.replace(/^Expand node (.+)\.$/, '展开节点 $1。');
  output = output.replace(/^Expand node (.+)$/, '展开节点 $1');
  output = output.replace(/^Explore neighbors (.+) and enqueue unvisited nodes\.$/, '检查邻居 $1，并将未访问节点入队。');
  output = output.replace(/^Discover nodes (.+) and push them into the queue\.$/, '发现节点 $1，并将它们加入队列。');
  output = output.replace(/^Reach target (.+) with shortest distance (.+)\.$/, '到达目标 $1，最短距离为 $2。');
  output = output.replace(/^Root the DFS at node (.+)\.$/, '以节点 $1 作为 DFS 根。');
  output = output.replace(/^Mark the subtree of node (.+) as nodes (.+)\.$/, '将节点 $1 的子树标记为节点 $2。');
  output = output.replace(/^Return subtree_size\((.+)\) = (.+)\.$/, '返回 subtree_size($1) = $2。');
  output = output.replace(/^Read a (\d+) x (\d+) grid for the DP problem\.$/, '读取一个 $1 x $2 的 DP 网格。');
  output = output.replace(/^Write (\d+) new DP cells?: (.+)\.$/, '写入 $1 个新的 DP 单元：$2。');
  output = output.replace(/^Update (\d+) DP cells? using previously solved subproblems\.$/, '用已求解的子问题更新 $1 个 DP 单元。');
  output = output.replace(/^The minimum path sum is (.+)\.$/, '最小路径和为 $1。');
  output = output.replace(/^dp\[(.+)\]\[(.+)\] = min\((.+), (.+)\) \+ grid\[(.+)\]\[(.+)\], so the best incoming sum is (.+)\.$/, 'dp[$1][$2] = min($3, $4) + grid[$5][$6]，因此最佳前驱和为 $7。');
  output = output.replace(/^Finish with answer (.+)\.$/, '最终答案为 $1。');
  output = output.replace(/^Place the two pointers at indices (.+) and (.+)\.$/, '将两个指针放在下标 $1 和 $2。');
  output = output.replace(/^Check (.+) \+ (.+) = (.+)\.$/, '检查 $1 + $2 = $3。');
  output = output.replace(/^Return (.+)\.$/, '返回 $1。');
  output = output.replace(/^Start with an empty window over (\d+) numbers\.$/, '在 $1 个数字上从空窗口开始。');
  output = output.replace(/^Extend the right edge to index (.+) and include (.+)\.$/, '将右边界扩展到下标 $1，并纳入 $2。');
  output = output.replace(/^Move the left edge forward to index (.+)\.$/, '将左边界前移到下标 $1。');
  output = output.replace(/^Update the best valid window length to (.+)\.$/, '将最佳合法窗口长度更新为 $1。');
  output = output.replace(/^Minimum valid length is (.+)\.$/, '最小合法长度为 $1。');
  output = output.replace(/^Window sum (.+) reaches the target (.+)\.$/, '窗口和 $1 已达到目标 $2。');
  output = output.replace(/^Window sum (.+) is still below (.+)\.$/, '窗口和 $1 仍小于 $2。');
  output = output.replace(/^Search the full range \[(.+), (.+)\] for (.+)\.$/, '在完整范围 [$1, $2] 中搜索 $3。');
  output = output.replace(/^Check mid = (.+), where the value is (.+)\.$/, '检查 mid = $1，此处值为 $2。');
  output = output.replace(/^Because (.+), narrow the next range to \[(.+), (.+)\]\.$/, '因为 $1，将下一段范围缩小到 [$2, $3]。');
  output = output.replace(/^Return index (.+)\.$/, '返回下标 $1。');
  output = output.replace(/^Read the array and prepare to answer range \[(.+), (.+)\]\.$/, '读取数组，并准备回答区间 [$1, $2]。');
  output = output.replace(/^Initialize prefix\[0\] = 0\.$/, '初始化 prefix[0] = 0。');
  output = output.replace(/^Build prefix sums up to prefix\[(.+)\]\.$/, '构建前缀和直到 prefix[$1]。');
  output = output.replace(/^Start with (\d+) singleton components\.$/, '从 $1 个单点连通分量开始。');
  output = output.replace(/^Merge the sets containing (.+) and (.+), reducing the component count to (.+)\.$/, '合并包含 $1 和 $2 的集合，将连通分量数降为 $3。');
  output = output.replace(/^All edges are processed; (.+) connected components remain\.$/, '所有边处理完毕，剩余 $1 个连通分量。');
  output = output.replace(/^Compute indegrees and start with node (.+) in the zero-indegree queue\.$/, '计算入度，并从零入度队列中的节点 $1 开始。');
  output = output.replace(/^Remove node (.+), append it to the ordering, and unlock nodes (.+)\.$/, '移除节点 $1，将其加入排序，并解锁节点 $2。');
  output = output.replace(/^Remove node (.+) and append it to the ordering\.$/, '移除节点 $1 并将其加入排序。');
  output = output.replace(/^Read (\d+) intervals\.$/, '读取 $1 个区间。');
  output = output.replace(/^Sort intervals by finishing time\.$/, '按结束时间排序区间。');
  output = output.replace(/^Skip interval \[(.+), (.+)\] because it overlaps with the last chosen end (.+)\.$/, '跳过区间 [$1, $2]，因为它与上一个已选结束点 $3 重叠。');
  output = output.replace(/^Take interval \[(.+), (.+)\] and update the last chosen end to (.+)\.$/, '选择区间 [$1, $2]，并将上一个已选结束点更新为 $3。');
  output = output.replace(/^Take interval \[(.+), (.+)\] as the first compatible choice\.$/, '选择区间 [$1, $2] 作为第一个兼容选择。');
  output = output.replace(/^Finish with a maximum of (.+) non-overlapping intervals\.$/, '最终最多选择 $1 个不重叠区间。');
  output = output.replace(/^Start from index (.+) and push (.+) onto the stack\.$/, '从下标 $1 开始，将 $2 入栈。');
  output = output.replace(/^Pop (.+) because those values are not greater than (.+), then push (.+)\.$/, '弹出 $1，因为这些值不大于 $2，然后将 $3 入栈。');
  output = output.replace(/^Pop (.+) because those values are not greater than (.+)\.$/, '弹出 $1，因为这些值不大于 $2。');
  output = output.replace(/^Process index (.+) with value (.+)\.$/, '处理下标 $1，值为 $2。');
  output = output.replace(/^Current answer view: (.+)\.$/, '当前答案视图：$1。');
  output = output.replace(/^Push (.+) onto the stack as a candidate for elements to its left\.$/, '将 $1 入栈，作为其左侧元素的候选值。');
  output = output.replace(/^Finished scanning; the next-greater answers are (.+)\.$/, '扫描完成；下一个更大值答案为 $1。');
  return output;
}

export function localizeDashboardText(language: DashboardLanguage, text: string | null | undefined): string {
  if (!text) return '';
  if (language === 'en') return text;
  return replaceKnownEnglish(text);
}

export function localizeJourneyStep(language: DashboardLanguage, step: JourneyStep): JourneyStep {
  if (language === 'en') return step;
  return {
    ...step,
    label: localizeDashboardText(language, step.label),
    summary: localizeDashboardText(language, step.summary),
  };
}

export function localizeTimelineEntry(language: DashboardLanguage, entry: JourneyTimelineEntry): JourneyTimelineEntry {
  if (language === 'en') return entry;
  const stage = stageText(language, entry.stageId);
  return {
    ...entry,
    title: localizeDashboardText(language, entry.title) || stage.title,
    summary: localizeDashboardText(language, entry.summary),
    steps: entry.steps.map((step) => localizeJourneyStep(language, step)),
    evidence: entry.evidence.map((line) => localizeDashboardText(language, line)),
    why: entry.why.map((line) => localizeDashboardText(language, line)),
  };
}

export function localizeStatusStrip(language: DashboardLanguage, status: JourneyStatusStrip): JourneyStatusStrip {
  if (language === 'en') return status;
  return {
    overallStatus: STATUS_TEXT_ZH[status.overallStatus] || localizeDashboardText(language, status.overallStatus),
    headline: localizeDashboardText(language, status.headline),
    detail: localizeDashboardText(language, status.detail),
    nextHint: localizeDashboardText(language, status.nextHint),
  };
}

export function localizeLiveProgress(language: DashboardLanguage, progress: LiveProgress): LiveProgress {
  if (language === 'en') return progress;
  return {
    ...progress,
    currentStepLabel: localizeDashboardText(language, progress.currentStepLabel),
    currentStepSummary: localizeDashboardText(language, progress.currentStepSummary),
    metrics: {
      ...progress.metrics,
      resultStatus: progress.metrics.resultStatus ? localizeDashboardText(language, progress.metrics.resultStatus) : null,
    },
  };
}

export function localizeAlgorithmStory(language: DashboardLanguage, story: AlgorithmVisualization): AlgorithmVisualization {
  if (language === 'en') return story;
  const familyLabel = FAMILY_LABELS[story.family]?.zh || story.family;
  const defaultTitle = story.family === 'unsupported' ? '算法过程' : `${familyLabel}过程演示`;
  return {
    ...story,
    mode: localizeDashboardText(language, story.mode),
    sampleSource: localizeDashboardText(language, story.sampleSource),
    sampleFocus: localizeDashboardText(language, story.sampleFocus),
    traceSource: story.traceSource ? localizeDashboardText(language, story.traceSource) : story.traceSource,
    title: localizeDashboardText(language, story.title) || defaultTitle,
    summary: localizeDashboardText(language, story.summary),
    validationNote: story.validationNote ? localizeDashboardText(language, story.validationNote) : story.validationNote,
    fallbackText: localizeDashboardText(language, story.fallbackText),
    steps: story.steps.map((step) => ({
      ...step,
      label: localizeDashboardText(language, step.label),
      caption: localizeDashboardText(language, step.caption),
    })),
  };
}

export function algorithmFamilyLabel(language: DashboardLanguage, family: AlgorithmVisualization['family']): string {
  return FAMILY_LABELS[family]?.[language] || family;
}

export function localizedBeatStatus(language: DashboardLanguage, status: string): string {
  if (language === 'en') return status;
  return STATUS_TEXT_ZH[status] || status;
}
