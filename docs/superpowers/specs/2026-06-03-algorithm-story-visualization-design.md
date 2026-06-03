# Algorithm Story Visualization Design

## Goal

在当前 dashboard 已经能展示“Agent 解题流程”的基础上，新增一个面向普通用户的 **Algorithm Story** 模块。

这个模块不再展示 LangGraph 节点流动，而是展示：

- 这道题的核心算法是什么
- 这个算法在题目的 `public sample` 上是如何工作的
- 用户可以通过一个小型可视化动画或逐步解释，直观看懂算法过程

第一版强调：

- **教学解释型**
- **解题结束后展示**
- **优先让普通用户看懂**

不追求：

- 任意最终 C++ 代码的真实逐行执行还原
- 所有题型的自动动画
- 求解过程中的实时算法动画

## Approved Product Decisions

本次设计基于以下已经确认的产品决策：

1. 第一版支持的算法家族只有：
   - `BFS / 图遍历`
   - `递归 / DFS`
   - `基础 DP`

2. 可视化输入来源固定为：
   - **题目的 public sample**

3. 可视化真实性标准为：
   - **教学解释型**
   - 展示这道题核心算法在 sample 上的工作方式
   - 不要求与最终生成代码逐行等价

4. 展示时机为：
   - **求解结束后**

5. 不支持题型或 sample 不适合展示时：
   - **回退到结构化文字解释**

6. 页面位置为：
   - **嵌入当前 solve 页面**
   - 位于 `Final Summary` 与 `Evidence Workbench` 之间

## Target User

目标用户仍然不是开发者，而是普通旁观者：

- 想看 AI 是怎么一步步做题的
- 看完 solve journey 后，还想进一步理解“这道题真正的算法是怎么跑的”
- 不关心底层 C++ 代码细节是否完全等价
- 更看重解释直观、步骤清晰、动画容易理解

## Scope

### In Scope

- solve 完成后的算法故事可视化
- 仅支持 `BFS / 递归-DFS / 基础 DP`
- 基于 `public sample` 生成教学解释轨迹
- 前端渲染三套可视化模板
- 不支持题型时回退到文字说明
- 将结构化结果放入已有 `artifact_snapshot`

### Out of Scope

- 任意题型通用可视化
- 实时可视化 solve 进行中间状态
- 对最终 C++ 代码做动态语义恢复
- 自动构造新的演示输入
- 复杂多算法混合题的全量可视化
- benchmark 专用页面或外部分享页改造

## Product Behavior

### Happy Path

当一道题 solve 完成后：

1. 系统先产生当前已有的 `Final Summary`
2. 然后生成一个 `Algorithm Story`
3. 用户在该模块中看到：
   - 算法家族标签，例如 `BFS`
   - 说明该演示来自 `Public Sample 1`
   - 8 到 20 个关键步骤
   - 每一步的自然语言说明
   - 与算法类型对应的可视化画布
4. 用户可手动逐步播放，也可点击右侧步骤列表直接跳转

### Fallback Path

当题目不属于第一版支持的三类算法，或 `public sample` 不适合展示时：

- 仍显示 `Algorithm Story` 卡片
- 但不展示动画画布
- 显示：
  - “This run does not yet support animated algorithm playback.”
  - 一段结构化算法解释：
    - 主算法是什么
    - 为什么这么做
    - 在 sample 上大致如何工作

这样页面结构保持稳定，不会因为支持与否而突变。

## Architecture

### High-Level Approach

第一版采用 **模板驱动的教学解释轨迹**，而不是解析任意最终 C++ 代码。

整体链路：

`final_state`
→ `algorithm story builder`
→ `algorithm_visualization artifact`
→ `artifact_snapshot`
→ `frontend renderer`

这里最关键的设计点是：

- **不修改 LangGraph 主路线**
- **不新增 solve 中间 phase**
- **只在 solve 结束后做一层后处理**

这样可以最大限度降低对现有 workflow、benchmark、verifier、hack 逻辑的影响。

### Why Post-Run Instead of In-Workflow

解题过程中，Agent 的主算法可能会变化：

- 先尝试一种方案
- verifier 打回后调整策略
- hack 阶段发现问题后再次修正

如果在中途就开始做算法动画，会出现解释跳变，用户体验会非常混乱。

因此第一版只允许：

- 在最终结果出现后
- 基于最终题解理解
- 生成稳定版算法故事

## Backend Design

### New Module

新增模块：

- `src/visualization/algorithm_story.py`

职责：

1. 判断题目是否属于第一版支持类型
2. 选择 `public sample`
3. 调用 LLM 生成结构化 `algorithm_visualization`
4. 在不支持或失败时生成 fallback 文字解释

推荐再拆一个 schema 文件：

- `src/visualization/story_types.py`

职责：

- 定义 `algorithm_visualization` 的结构化 schema
- 约束 family、step、state 字段

### Input Sources

该模块可读取：

- `problem.description`
- `problem.public_tests`
- `problem.canonical`
- `problem.tags_selected`
- `plan.algorithm_choice`
- `solution.code`
- `verification`
- `tests`

其中，family 判定优先参考：

1. `plan.algorithm_choice`
2. `problem.canonical`
3. `problem.tags_selected`

最终代码仅作为辅助参考，不作为真实执行轨迹来源。

### LLM Configuration

新增 role：

- `llm.roles.algorithm_visualizer`

新增 prompt：

- `algorithm_visualization.system`
- `algorithm_visualization.user`

这样可以把它与 `code / verifier / hacker` 的 prompt 责任分离。

### Sample Selection Policy

第一版固定使用：

- `public_tests[0]`

如果 `public_tests[0]` 里包含多组 testcase，允许 LLM 在返回数据中标注：

- `sample_focus`

例如：

- `first testcase inside sample 1`
- `smallest subcase inside sample 1`

如果 sample 明显不适合画：

- 直接 fallback
- 不允许自动生成新输入

### Fallback Rules

出现以下任一情况时，直接返回 fallback：

1. 没有 `public sample`
2. family 不属于 `bfs / dfs_recursion / basic_dp`
3. sample 太大，不适合第一版展示
4. LLM 输出 JSON 不合法
5. 关键字段缺失

fallback 返回：

- `supported: false`
- `family: "unsupported"`
- `fallback_text: "..."`

## Data Contract

### Artifact Field

在现有 `artifact_snapshot` 中新增：

```json
{
  "algorithm_visualization": {
    "supported": true,
    "family": "bfs",
    "mode": "teaching",
    "sample_source": "public_test_1",
    "sample_focus": "first testcase inside sample 1",
    "title": "Breadth-First Expansion on the Sample Graph",
    "summary": "We expand the queue layer by layer from the start node until the target is reached.",
    "steps": [
      {
        "step": 1,
        "label": "Initialize queue",
        "caption": "Put the start node into the queue and mark it visited.",
        "state": {}
      }
    ],
    "fallback_text": ""
  }
}
```

### Common Fields

所有支持型 family 至少包含：

- `supported`
- `family`
- `mode`
- `sample_source`
- `sample_focus`
- `title`
- `summary`
- `steps`
- `fallback_text`

其中：

- `mode` 固定为 `teaching`
- `sample_source` 第一版固定为 `public_test_1`
- `steps` 数量硬限制为 `8-20`

### BFS State Shape

```json
{
  "graph": {
    "nodes": [],
    "edges": []
  },
  "queue": [],
  "visited": [],
  "current": null,
  "distance": {}
}
```

### DFS / Recursion State Shape

```json
{
  "tree": {
    "nodes": [],
    "edges": []
  },
  "call_stack": [],
  "current_call": null,
  "returned_values": {}
}
```

### Basic DP State Shape

```json
{
  "table": [],
  "highlight_cells": [],
  "current_transition": "",
  "input_view": {}
}
```

## Frontend Design

### Placement

在当前 solve 页面中插入：

`Final Summary`
→ `Algorithm Story`
→ `Evidence Workbench`

这样符合用户理解顺序：

1. 先知道结果如何
2. 再看算法在 sample 上怎么跑
3. 最后看代码、测试、反例等证据

### Main Container

新增组件：

- `dashboard/frontend/src/components/AlgorithmStoryCard.tsx`

职责：

- 接收 `algorithm_visualization`
- 判断 `supported`
- 选择正确 renderer
- fallback 时显示文字解释

### Renderer Components

新增三个 renderer：

- `algorithm-story/BfsStoryView.tsx`
- `algorithm-story/DfsRecursionStoryView.tsx`
- `algorithm-story/BasicDpStoryView.tsx`

#### BFS Renderer

展示：

- 图节点和边
- 当前队列
- 当前访问节点
- visited 染色

#### DFS / Recursion Renderer

展示：

- 调用树或子问题树
- 当前调用栈
- 当前递归帧高亮
- 返回路径高亮

#### Basic DP Renderer

展示：

- DP 表格
- 当前填充单元格
- 转移来源格子
- 当前转移说明

### Interaction Model

第一版交互规则：

- 默认不自动播放
- 用户点击 `Play` 后逐步前进
- 支持 `Prev / Next`
- 支持点击步骤列表跳转
- 每步都显示一句自然语言解释

### Fallback UI

即使不支持动画，也显示 `Algorithm Story` 卡片，内容包括：

- 标题
- fallback 提示
- 一段结构化文字解释

不允许模块直接消失。

## File Plan

### Backend

- Create: `src/visualization/algorithm_story.py`
- Create: `src/visualization/story_types.py`
- Modify: `main.py`
- Modify: `config/models.yaml`
- Modify: `config/prompt_template.yaml`
- Create: `tests/visualization/test_algorithm_story.py`
- Create: `tests/test_artifact_snapshot_visualization.py`

### Frontend

- Create: `dashboard/frontend/src/components/AlgorithmStoryCard.tsx`
- Create: `dashboard/frontend/src/components/algorithm-story/BfsStoryView.tsx`
- Create: `dashboard/frontend/src/components/algorithm-story/DfsRecursionStoryView.tsx`
- Create: `dashboard/frontend/src/components/algorithm-story/BasicDpStoryView.tsx`
- Modify: `dashboard/frontend/src/types/artifacts.ts`
- Modify: `dashboard/frontend/src/utils/extractRunArtifacts.ts`
- Modify: `dashboard/frontend/src/App.tsx`
- Modify: `dashboard/frontend/src/styles/journey.css`

## Validation Plan

### Supported Cases

至少验证三类题：

1. `BFS / 图遍历`
2. `递归 / DFS`
3. `基础 DP`

每类都要求：

- `supported = true`
- `family` 正确
- `steps` 数量在 `8-20`
- 画布与步骤说明同步

### Fallback Cases

至少验证两类回退：

1. 不支持题型
2. 没有合适 `public sample`

要求：

- `supported = false`
- 前端仍显示 `Algorithm Story`
- 文字解释存在
- 页面不报错、不空白

### Engineering Verification

Python 侧：

- family 判定测试
- schema 完整性测试
- fallback 测试
- `artifact_snapshot` 拼装测试

Frontend 侧：

- `npm run build`
- 用固定 replay JSON 做三类 renderer 的手工 smoke

## Risks And Mitigations

### Risk 1: LLM 解释与最终代码不完全一致

缓解：

- 第一版明确标注为 `Teaching Mode`
- 不宣传为真实执行还原
- family 仅作为题解解释，而不是代码动态调试

### Risk 2: public sample 不适合展示

缓解：

- 第一版严格 fallback
- 不强行生成差的动画

### Risk 3: 多算法混合题难以分类

缓解：

- 第一版只支持单一主算法族
- 混合题直接 fallback

### Risk 4: 步数太多导致前端臃肿

缓解：

- 强制 `8-20` 步
- 只保留关键步骤，不做逐语句回放

## Non-Goals

第一版明确不做：

- 任意最终 C++ 代码的真实执行动画
- solve 过程中的实时算法动画
- 不支持题型的近似模板强配
- 自动生成新的可视化输入
- 多算法联合复杂演示

## Summary

第一版 `Algorithm Story` 的核心定位是：

- **后处理**
- **教学解释型**
- **仅 3 类模板**
- **基于 public sample**
- **解题结束后展示**
- **不支持时稳定回退**

这是在当前 `algorithm-agent` 架构里，风险最低、实现最稳、最容易让普通用户真正看懂的一条路线。
