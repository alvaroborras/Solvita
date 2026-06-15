import { useEffect } from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { DashboardI18nProvider, useI18n } from '../i18n';
import type { FailureAnalysis } from '../utils/failureAnalysis';
import FailureAnalysisCard from './FailureAnalysisCard';

const analysis: FailureAnalysis = {
  headline: 'The solver ran out of repair budget.',
  summary: 'The run kept looping through codegen and repair, but never reached an accepted solution before the iteration budget ran out.',
  rootCause: 'The workflow kept repairing the candidate, but never gathered enough evidence to accept it before the iteration budget ran out.',
  chain: [
    {
      id: 'codegen-1',
      stageLabel: 'Codegen',
      title: 'Generating & Testing Code',
      summary: 'Attempt 3 failed to compile cleanly and needs repair.',
      status: 'warning',
      evidence: ['Compile status: failure'],
    },
    {
      id: 'run-ended-max-iterations',
      stageLabel: 'Run Ended',
      title: 'Repair budget exhausted',
      summary: 'The workflow hit the iteration cap before it could produce an accepted solution.',
      status: 'failed',
      evidence: ['iterations: 5', 'visible pass rate: 0%'],
    },
  ],
  signals: {
    compilationErrors: ["missing ';' after return"],
    suggestedFixes: ['Add the missing semicolon.'],
    hackFailures: ['type: WA | Cycle handling is incorrect. | expected 2 / actual 3'],
    errorEvents: ['Workflow execution failed: sandbox timeout'],
    executionLogTail: ['Hack memory: no items to settle'],
  },
};

function ForceChinese() {
  const { setLanguage } = useI18n();
  useEffect(() => {
    setLanguage('zh');
  }, [setLanguage]);
  return null;
}

describe('FailureAnalysisCard', () => {
  it('localizes the full failure analysis module in Chinese mode', async () => {
    render(
      <DashboardI18nProvider>
        <ForceChinese />
        <FailureAnalysisCard analysis={analysis} />
      </DashboardI18nProvider>,
    );

    expect(await screen.findByText('失败分析')).toBeInTheDocument();
    expect(screen.getByText('需要修复')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '求解器耗尽修复预算。' })).toBeInTheDocument();
    expect(screen.getByText('本次运行持续在代码生成和修复间循环，但在迭代预算耗尽前未达到可接受解法。')).toBeInTheDocument();
    expect(screen.getByText('可能根因')).toBeInTheDocument();
    expect(screen.getByText('工作流持续修复候选解，但在迭代预算耗尽前始终没有收集到足够证据来接受它。')).toBeInTheDocument();
    expect(screen.getByText('失败链路')).toBeInTheDocument();
    expect(screen.getByText('代码生成')).toBeInTheDocument();
    expect(screen.getByText('运行结束')).toBeInTheDocument();
    expect(screen.getByText('修复预算已耗尽')).toBeInTheDocument();
    expect(screen.getByText('第 3 次尝试未能干净编译，需要修复。')).toBeInTheDocument();
    expect(screen.getByText('迭代次数：5')).toBeInTheDocument();
    expect(screen.getByText('可见通过率：0%')).toBeInTheDocument();
    expect(screen.getByText('结构化信号')).toBeInTheDocument();
    expect(screen.getByText('编译错误')).toBeInTheDocument();
    expect(screen.getByText('建议修复')).toBeInTheDocument();
    expect(screen.getByText('Hack 失败')).toBeInTheDocument();
    expect(screen.getByText('运行时错误')).toBeInTheDocument();
    expect(screen.getByText('执行日志尾部')).toBeInTheDocument();
    expect(screen.getByText('类型：WA | Cycle handling is incorrect. | 期望 2 / 实际 3')).toBeInTheDocument();
    expect(screen.getByText('Hack 记忆：暂无可结算条目')).toBeInTheDocument();
  });
});
