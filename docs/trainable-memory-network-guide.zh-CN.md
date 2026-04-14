# Trainable Memory 网络位置、使用方式与拆卸说明

## 1. 文档目的

本文档说明当前主分支中与 `Oracle` / `Hacker` 训练相关的“网络”实际指什么、代码位于哪里、训练结果落在什么位置、运行时如何接入，以及在需要时如何进行软拆卸或硬拆卸。

这里的“网络”并不是单一的深度神经网络 checkpoint，而是以 **namespace-isolated trainable memory** 为核心的可学习策略层。其基础形式是一个带稀疏权重的上下文 bandit / 二部图打分网络，并以 SQLite 数据库与 `policy.json` 共同持久化训练结果。

---

## 2. 关于训练结果目录的说明

### 2.1 旧结果目录

远程仓库历史中曾存在：

- `test_mem/hack/memory.db`
- `test_mem/hack/policy.json`

这些文件体积很小，只能视为早期测试/样例数据，不代表当前正式 Oracle / Hacker 训练的最新结果。

### 2.2 新结果目录

本次起，最新正式训练结果统一跟踪在：

- `artifacts/trainable_memory/latest/oracle/`
- `artifacts/trainable_memory/latest/hacker/`

每个模块目录下默认包含：

- `memory.db.gz`：从 live SQLite 导出的压缩快照
- `policy.json`：当前 namespace 的权重文件
- `*_checkpoint.json`：当前训练断点文件
- `manifest.json`：导出时间、来源路径、文件大小与 SHA256

### 2.3 为什么使用压缩后的 `memory.db.gz`

Oracle 的最新 `memory.db` 体积较大，已超过普通 Git 仓库中直接跟踪单个二进制文件时更稳妥的体量范围。为避免：

- 单文件过大导致推送失败
- 仓库体积膨胀过快
- 后续拉取与 diff 体验恶化

当前主线选择跟踪 **一致性快照导出的压缩版本**，而不是直接跟踪运行中的 live `memory.db` 原文件。

---

## 3. 训练网络的代码位置

### 3.1 通用 Trainable Memory 层

当前远程主分支中的核心 trainable memory 网络位于：

- `src/memory/client.py`
- `src/memory/store.py`
- `src/memory/policy.py`
- `src/memory/featurizer.py`
- `src/memory/types.py`
- `src/memory/seeds/`

其中：

#### `src/memory/policy.py`

这里是当前“网络”本体。其不是深度学习框架中的神经网络权重文件，而是一个上下文 bandit 形式的打分模型。核心评分形式为：

\[
score(item) = bias[item] + \sum W[feature, item]
\]

其中：

- `feature` 来自问题 canonical 特征、FSM 状态、失败类型、尝试轮次等
- `item` 是 memory item
- `W` 是稀疏边权
- `bias` 是 item 的全局偏置项

#### `src/memory/client.py`

这里是统一入口，负责：

- 读取配置中的 `trainable_memory.enabled`
- 初始化 namespace 对应的 `MemoryStore`
- 载入 `policy.json`
- 调用 policy 对候选 memory item 打分并选择
- 将选中结果格式化为 prompt injection
- 在结果结算时调用 `log_event(...)`

#### `src/memory/store.py`

这里负责 SQLite 落盘。当前 namespace 对应数据库为：

- `plan/memory.db`
- `solve/memory.db`
- `hack/memory.db`
- `oracle/memory.db`

数据库中至少包含：

- `items`
- `events`

其中 `events` 表中还包含 `metadata_json`，用于存放 Oracle / Hacker 的结构化训练信号。

---

## 4. Oracle 相关网络与实现位置

### 4.1 Oracle 在主流程中的接线位置

Oracle 相关接线主要在：

- `src/nodes/generate_tests.py`
- `src/nodes/update_oracle_memory.py`
- `src/graph/workflow.py`

其中：

- `generate_tests.py` 负责调用 `MemoryClient(namespace=MemoryNamespace.ORACLE, ...)`
- `update_oracle_memory.py` 负责在结算阶段将 reward 和结构化 metadata 写回 Oracle memory

### 4.2 Oracle 专属高层策略层

除了通用的 `src/memory/`，Oracle 还有一层专属逻辑：

- `src/oracle/oracle_memory_db.py`
- `src/oracle/oracle_memory_runtime.py`
- `src/oracle/oracle_memory_policy.py`

这一层的作用是：

1. 将 Oracle 训练过程中的 observation 级信号规范化存入数据库
2. 保存 Oracle action 统计量
3. 保存 Oracle model snapshot
4. 在 runtime 上做 Oracle memory gate decision

### 4.3 Oracle 对应的权重与结果文件

Oracle 最新训练结果在当前主线中的跟踪位置是：

- `artifacts/trainable_memory/latest/oracle/memory.db.gz`
- `artifacts/trainable_memory/latest/oracle/policy.json`
- `artifacts/trainable_memory/latest/oracle/oracle_checkpoint.json`
- `artifacts/trainable_memory/latest/oracle/manifest.json`

其中：

#### `policy.json`

这是通用 trainable memory 层中 Oracle namespace 的权重文件，对应：

- `bias`
- `weights`
- `learning_rate`
- `epsilon`

#### `memory.db.gz`

解压后对应 Oracle namespace 的主 SQLite 数据库：

- `oracle/memory.db`

其中不仅有通用的 `items` / `events`，还包含 Oracle 专属表，例如：

- `oracle_observations`
- `oracle_action_stats`
- `oracle_model_snapshots`

因此，Oracle 的“高层策略模型快照”并不是单独的 `.pt` / `.bin` 文件，而是存放在 `oracle_model_snapshots` 表中。

---

## 5. Hacker 相关网络与实现位置

### 5.1 Hacker 在主流程中的接线位置

Hacker 相关接线主要在：

- `src/nodes/hack_test.py`
- `src/nodes/settle_hacker_memory.py`
- `src/graph/workflow.py`

其中：

- `hack_test.py` 通过 `MemoryClient(namespace=MemoryNamespace.HACK, ...)` 注入 adversarial strategy
- `settle_hacker_memory.py` 在 terminal round 后计算 reward，并将结构化 metadata 写回 Hack memory

### 5.2 Hacker 对应的权重与结果文件

Hacker 最新训练结果在当前主线中的跟踪位置是：

- `artifacts/trainable_memory/latest/hacker/memory.db.gz`
- `artifacts/trainable_memory/latest/hacker/policy.json`
- `artifacts/trainable_memory/latest/hacker/hacker_checkpoint.json`
- `artifacts/trainable_memory/latest/hacker/manifest.json`

其中：

#### `policy.json`

这是 Hack namespace 的通用 trainable memory 权重文件。

#### `memory.db.gz`

解压后对应：

- `hack/memory.db`

其核心内容主要是：

- `items`
- `events`

与 Oracle 相比，Hacker 没有额外一层像 `oracle_model_snapshots` 这样的专属高层模型表；其学习信号主要通过：

- `route_used`
- `hack_result`
- `failure_type`
- `generator_failure_kind`
- `compile_failures`
- `reward`

等字段写入 `events.metadata_json`。

---

## 6. 运行时如何使用这套网络

### 6.1 打开方式

当前网络的总开关在配置中：

```python
config["trainable_memory"]["enabled"] = True
```

当该开关为 `True` 时：

1. `MemoryClient` 初始化 namespace 对应的 SQLite store
2. 从 `policy.json` 载入权重
3. 依据当前 observation 抽取 feature keys
4. 对候选 memory item 打分并选择
5. 将选中结果注入相应模块
6. 在结算阶段用 reward 更新权重并写回 DB

### 6.2 Oracle 的使用方式

Oracle 主要在：

- `generate_tests_node`
- `update_oracle_memory_node`

中使用。

运行时过程可概括为：

1. 根据问题特征从 Oracle memory 中选取 candidate family / strategy
2. 将相应策略信息注入 Oracle 流程
3. 完成 checker / solver / artifact 认证
4. 将 `oracle_event_metadata` 与 reward 写回 Oracle memory

### 6.3 Hacker 的使用方式

Hacker 主要在：

- `hack_test_node`
- `settle_hacker_memory`

中使用。

运行时过程可概括为：

1. 从 Hack memory 中检索 adversarial strategy
2. 将其注入 code analyst / cascading router
3. 生成攻击输入并执行
4. 在 terminal round 上结算 reward
5. 将结构化攻击信息写回 Hack memory

### 6.4 Benchmark 模式下的特殊情况

在 benchmark pipeline 模式中，主线当前显式关闭 trainable memory：

```python
trainable_memory["enabled"] = False
```

也就是说，benchmark 目前默认评估的是：

- Oracle / Hacker 主流程逻辑
- 但不让这套学习网络继续参与在线学习

这说明当前系统本身已经支持一种“软拆卸”的运行方式。

---

## 7. 可拆卸性：怎么拆

当前网络是可拆卸的，但要区分三种层级。

### 7.1 方案一：软拆卸（推荐）

这是最小改动方案，只关闭 trainable memory 学习层，而保留 Oracle / Hacker 主流程。

做法：

```python
config["trainable_memory"]["enabled"] = False
```

效果：

- `MemoryClient` 仍可能被调用
- 但会退化为 no-op
- 不再注入 memory item
- 不再写 event
- 不再更新 `policy.json`
- `memory.db` 不再继续参与学习

优点：

- 改动最小
- 风险最低
- 不影响主流程结构
- Oracle / Hacker 功能仍可保留

适用场景：

- 保留模块逻辑
- 停用学习层
- 做无记忆对照实验

### 7.2 方案二：Oracle 半拆卸

如果只想关闭 Oracle 专属高层 memory runtime，而不是关掉整个 trainable memory 网络，可设置：

```python
config["trainable_memory"]["oracle_memory_mode"] = "off"
```

效果：

- Oracle 的高层 gate / snapshot runtime 逻辑关闭
- 但如果 `trainable_memory.enabled` 仍为 `True`，通用 memory 网络依然还在

因此，这不是“彻底拆 Oracle 网络”，而只是关闭 Oracle 的高层 runtime mode。

### 7.3 方案三：硬拆卸（结构拆卸）

如果要彻底把 Oracle / Hacker 从 pipeline 中移除，就必须修改：

- `src/graph/workflow.py`

例如：

#### 移除 Oracle learning path

需要处理：

- `update_oracle_memory_node`
- `generate_tests_node` 中 Oracle memory 注入逻辑

#### 移除 Hacker phase

需要处理：

- `hacker_phase`
- `hack_test_node`
- `settle_hacker_memory`
- `hack_outcome_routing`
- `phase_transition_3`

这已经不是简单开关，而是 workflow 级重构。

---

## 8. 推荐拆卸策略

如果你的目标只是“让训练网络不再工作”，推荐顺序如下：

### 推荐方案 A

```python
trainable_memory.enabled = False
```

并保留 Oracle / Hacker 主流程。

### 推荐方案 B

在方案 A 基础上，再归档结果文件：

- `oracle/memory.db`
- `oracle/policy.json`
- `hack/memory.db`
- `hack/policy.json`

这适合做：

- 学习层停用
- 结果冻结
- 对照实验归档

### 不推荐直接做的方案

直接修改 `workflow.py` 硬拆 Oracle / Hacker。  
这种方式会影响：

- phase routing
- Hack→CodeGen 回环
- Oracle/Hacker 的结算逻辑

适合作为结构重构，不适合作为最小改动拆卸。

---

## 9. 一句话结论

当前主分支中的“网络部分”主要位于 `src/memory/`，其中 `src/memory/policy.py` 是通用 trainable memory 网络的权重实现，`src/memory/client.py` 与 `src/memory/store.py` 负责运行时接入与 SQLite 持久化；Oracle 还额外拥有 `src/oracle/oracle_memory_db.py`、`src/oracle/oracle_memory_runtime.py` 与 `src/oracle/oracle_memory_policy.py` 这一层专属高层策略逻辑。最新正式训练结果已统一跟踪在 `artifacts/trainable_memory/latest/` 下，旧的 `test_mem/hack/*` 应视为历史测试结果。该网络是可拆卸的，推荐方式是通过 `trainable_memory.enabled = False` 做软拆卸；若要彻底移除 Oracle / Hacker，则需要进一步修改顶层 workflow，属于结构重构而非配置开关。
