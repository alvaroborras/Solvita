import { describe, expect, it } from 'vitest';

import type { AlgorithmVisualization } from './types/artifacts';
import type { JourneyStatusStrip, JourneyTimelineEntry } from './types/journey';
import {
  localizeAlgorithmStory,
  localizeDashboardText,
  localizeStatusStrip,
  localizeTimelineEntry,
} from './i18n';

function hackEntry(overrides: Partial<JourneyTimelineEntry> = {}): JourneyTimelineEntry {
  return {
    id: 'hack-3',
    stageId: 'hack',
    visit: 3,
    title: 'Adversarial Hack Testing',
    summary: 'Hack round 3 did not find a breaking input.',
    status: 'completed',
    startedAt: 1,
    endedAt: 2,
    startSeq: 10,
    endSeq: 12,
    steps: [
      {
        id: 'hack-3-step-11',
        label: 'Try to break the solution',
        summary: 'Trying to generate a breaking input.',
        status: 'completed',
        ts: 1.5,
        seq: 11,
      },
    ],
    evidence: ['Hack round: 3'],
    why: ['Late-stage breaking is the last chance to catch bugs before declaring success.'],
    ...overrides,
  };
}

describe('dashboard Chinese localization helpers', () => {
  it('localizes dynamic hack timeline text', () => {
    const entry = localizeTimelineEntry('zh', hackEntry());

    expect(entry.title).toBe('对抗 Hack 检验');
    expect(entry.summary).toBe('第 3 轮 Hack 未找到破坏性输入。');
    expect(entry.steps[0].label).toBe('尝试击破解法');
    expect(entry.steps[0].summary).toBe('正在生成破坏性输入。');
    expect(entry.evidence).toEqual(['Hack 轮次：3']);
    expect(entry.why).toEqual(['末段破坏测试是在宣布成功前捕获缺陷的最后机会。']);
  });

  it('localizes active hack status strip text', () => {
    const status: JourneyStatusStrip = {
      overallStatus: 'Hacking',
      headline: 'Now in Hack, pass 3',
      detail: 'Hack round 3 did not find a breaking input.',
      nextHint: 'Next: either declare the solver safe or send a breaking input back for repair.',
    };

    expect(localizeStatusStrip('zh', status)).toEqual({
      overallStatus: 'Hack 中',
      headline: '当前在 Hack 检验，第 3 次访问',
      detail: '第 3 轮 Hack 未找到破坏性输入。',
      nextHint: '下一步：确认解法安全，或把破坏性输入送回修复。',
    });
  });

  it('localizes active full testgen status strip text', () => {
    const status: JourneyStatusStrip = {
      overallStatus: 'Running',
      headline: 'Now in Full Testgen',
      detail: 'Expanding coverage with broader generated examples.',
      nextHint: 'Next: move into code generation with a stronger test bed.',
    };

    expect(localizeStatusStrip('zh', status)).toEqual({
      overallStatus: '运行中',
      headline: '当前在完整测例生成',
      detail: '正在用更广的生成样例扩展覆盖。',
      nextHint: '下一步：带着更强测试集进入代码生成。',
    });
  });

  it('localizes phase labels and default stage summaries from backend events', () => {
    const abstractEntry = localizeTimelineEntry('zh', hackEntry({
      id: 'read_problem-1',
      stageId: 'read_problem',
      title: 'Abstracting Problem',
      summary: 'Turn the statement into structured constraints and tags.',
      why: [],
      evidence: [],
      steps: [
        {
          id: 'read_problem-1-step-1',
          label: 'Abstracting Problem',
          summary: 'Turn the statement into structured constraints and tags.',
          status: 'completed',
          ts: 1,
          seq: 1,
        },
      ],
    }));

    const testgenEntry = localizeTimelineEntry('zh', hackEntry({
      id: 'full_testgen-1',
      stageId: 'full_testgen',
      title: 'Generating Tests',
      summary: 'Generated 51 broader tests before trusting the solver.',
      why: [],
      evidence: [],
      steps: [
        {
          id: 'full_testgen-1-step-1',
          label: 'Generating Tests',
          summary: 'Expand coverage when risk is high or checks ask for more evidence.',
          status: 'completed',
          ts: 2,
          seq: 2,
        },
      ],
    }));

    expect(abstractEntry.title).toBe('题目抽象');
    expect(abstractEntry.summary).toBe('将题面转成结构化约束和标签。');
    expect(abstractEntry.steps[0].label).toBe('题目抽象');
    expect(testgenEntry.title).toBe('生成测试');
    expect(testgenEntry.summary).toBe('在信任求解器前生成了 51 个更广覆盖的测试。');
    expect(testgenEntry.steps[0].summary).toBe('在风险较高或需要更多证据时扩展覆盖。');
  });

  it('localizes codegen and planning phase text from backend events', () => {
    const codegenEntry = localizeTimelineEntry('zh', hackEntry({
      id: 'codegen-1',
      stageId: 'codegen',
      title: 'Generating & Testing Code',
      summary: 'Draft, compile, and run the current solver attempt.',
      why: [],
      evidence: [
        'Attempt: 1',
        'Compile status: success',
        'Planned strategy: P: Iterate through the array once while maintaining a hash map from previously seen value to its index.',
      ],
      steps: [
        {
          id: 'codegen-1-step-1',
          label: 'Planning Strategy',
          summary: 'Using a planner to choose a stronger strategy before coding.',
          status: 'completed',
          ts: 3,
          seq: 3,
        },
        {
          id: 'codegen-1-step-2',
          label: 'Generating & Testing Code',
          summary: 'Draft, compile, and run the current solver attempt.',
          status: 'active',
          ts: 4,
          seq: 4,
        },
      ],
    }));

    expect(codegenEntry.title).toBe('生成并测试代码');
    expect(codegenEntry.summary).toBe('编写、编译并运行当前求解尝试。');
    expect(codegenEntry.steps[0].label).toBe('规划策略');
    expect(codegenEntry.steps[1].label).toBe('生成并测试代码');
    expect(codegenEntry.steps[1].summary).toBe('编写、编译并运行当前求解尝试。');
    expect(codegenEntry.evidence).toEqual([
      '尝试：1',
      '编译状态：成功',
      '规划策略：P：单次遍历数组，同时维护从已见数值到其下标的哈希表。',
    ]);
  });

  it('localizes algorithm story shell and common generated playback text', () => {
    const story: AlgorithmVisualization = {
      supported: true,
      family: 'bfs',
      mode: 'teaching',
      sampleSource: 'public sample',
      sampleFocus: 'first sample',
      traceSource: 'execution-trace',
      sampleInput: '1\n',
      sampleOutput: '1\n',
      title: 'Breadth-first search walkthrough',
      summary: 'Trace the queue while BFS visits the graph.',
      steps: [
        {
          step: 1,
          label: 'Build the graph',
          caption: 'The emitted solution builds adjacency lists from the sample edges.',
          state: { queue: [], visited: [] },
        },
        {
          step: 2,
          label: 'Start at node 1',
          caption: 'Initialize the queue with the starting node.',
          state: { queue: [1], visited: [1] },
        },
      ],
      sampleValidated: true,
      sampleMatches: true,
      validationNote: 'The emitted solution matches the sample output on this trace.',
      fallbackText: 'This run does not yet support animated algorithm playback.',
    };

    const localized = localizeAlgorithmStory('zh', story);

    expect(localized.title).toBe('广度优先搜索过程演示');
    expect(localized.summary).toBe('跟踪 BFS 访问图时队列的变化。');
    expect(localized.sampleSource).toBe('公开样例');
    expect(localized.sampleFocus).toBe('第一个样例');
    expect(localized.traceSource).toBe('执行轨迹');
    expect(localized.steps[0].label).toBe('构建图');
    expect(localized.steps[0].caption).toBe('该解法会根据样例边构建邻接表。');
    expect(localized.steps[1].label).toBe('从节点 1 开始');
    expect(localized.steps[1].caption).toBe('用起始节点初始化队列。');
    expect(localized.validationNote).toBe('该解法在这条轨迹上输出与样例输出一致。');
    expect(localized.fallbackText).toBe('本次运行暂不支持算法动画回放。');
  });

  it('localizes parameterized BFS story labels and captions', () => {
    expect(localizeDashboardText('zh', 'Start BFS at node 1')).toBe('从节点 1 开始 BFS');
    expect(localizeDashboardText('zh', 'Expand node 7')).toBe('展开节点 7');
    expect(localizeDashboardText('zh', 'Explore neighbors 2, 3 and enqueue unvisited nodes.')).toBe('检查邻居 2, 3，并将未访问节点入队。');
    expect(localizeDashboardText('zh', 'Build the graph')).toBe('构建图');
  });

  it('localizes runtime mode and result badges', () => {
    expect(localizeDashboardText('zh', 'live')).toBe('实时');
    expect(localizeDashboardText('zh', 'connected')).toBe('已连接');
    expect(localizeDashboardText('zh', 'ready')).toBe('已就绪');
    expect(localizeDashboardText('zh', 'success')).toBe('成功');
    expect(localizeDashboardText('zh', 'SAFE')).toBe('安全');
    expect(localizeDashboardText('zh', 'not used')).toBe('未使用');
  });

  it('localizes algorithm trace titles, sources, and representative non-BFS families', () => {
    expect(localizeDashboardText('zh', 'BFS Code Trace')).toBe('BFS 代码轨迹');
    expect(localizeDashboardText('zh', 'A variable-level trace captured from the emitted C++ BFS implementation.')).toBe('从生成的 C++ BFS 实现中捕获的变量级轨迹。');
    expect(localizeDashboardText('zh', 'execution-trace')).toBe('执行轨迹');
    expect(localizeDashboardText('zh', 'public_test_1')).toBe('公开测试 1');
    expect(localizeDashboardText('zh', 'Grid DP Code Trace')).toBe('网格 DP 代码轨迹');
    expect(localizeDashboardText('zh', 'Take node 4')).toBe('取出节点 4');
    expect(localizeDashboardText('zh', 'Process edge 2-5')).toBe('处理边 2-5');
    expect(localizeDashboardText('zh', 'Update dp[2][3]')).toBe('更新 dp[2][3]');
    expect(localizeDashboardText('zh', 'Enter dfs(7)')).toBe('进入 dfs(7)');
  });

  it('localizes generated playback changes across algorithm families', () => {
    expect(localizeDashboardText('zh', 'Initialize the base case at the top-left corner.')).toBe('初始化左上角基础状态。');
    expect(localizeDashboardText('zh', 'Update 2 DP cells using previously solved subproblems.')).toBe('用已求解的子问题更新 2 个 DP 单元。');
    expect(localizeDashboardText('zh', 'The minimum path sum is 9.')).toBe('最小路径和为 9。');
    expect(localizeDashboardText('zh', 'dp[2][3] = min(4, 5) + grid[2][3], so the best incoming sum is 4.')).toBe('dp[2][3] = min(4, 5) + grid[2][3]，因此最佳前驱和为 4。');
    expect(localizeDashboardText('zh', 'Pop 3, 2 because those values are not greater than 5, then push 5.')).toBe('弹出 3, 2，因为这些值不大于 5，然后将 5 入栈。');
  });

  it('localizes replay and evidence workbench text', () => {
    expect(localizeDashboardText('zh', 'Replay Progress')).toBe('回放进度');
    expect(localizeDashboardText('zh', 'Scrub the run by stage or exact event position')).toBe('按阶段或精确事件位置拖动回放');
    expect(localizeDashboardText('zh', 'The map, timeline, and live progress panels stay synced to the replay cursor.')).toBe('地图、时间线和实时进度面板会与回放游标保持同步。');
    expect(localizeDashboardText('zh', 'Evidence Workbench')).toBe('证据工作台');
    expect(localizeDashboardText('zh', 'Code, tests, result, and counterexamples in one place')).toBe('集中查看代码、测试、结果和反例');
    expect(localizeDashboardText('zh', 'code')).toBe('代码');
    expect(localizeDashboardText('zh', 'tests')).toBe('测试');
    expect(localizeDashboardText('zh', 'counterexample')).toBe('反例');
    expect(localizeDashboardText('zh', 'emitted solution')).toBe('生成的解法');
    expect(localizeDashboardText('zh', 'version')).toBe('版本');
    expect(localizeDashboardText('zh', 'lines')).toBe('行');
    expect(localizeDashboardText('zh', 'No emitted solution snapshot is available yet for this run.')).toBe('本次运行暂无生成解法快照。');
  });

  it('localizes memory settlement and update log lines', () => {
    expect(localizeDashboardText('zh', 'Hack memory: no items to settle')).toBe('Hack 记忆：暂无可结算条目');
    expect(localizeDashboardText('zh', 'Hacker memory: no items to update')).toBe('Hacker 记忆：暂无可更新条目');
  });
});
