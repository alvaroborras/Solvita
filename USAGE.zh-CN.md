# Solvita CLI 使用说明

`dev` 分支在 `supplement_upload` 的最新后端之上叠加了 `solvita-cli` 的 Ink/React 终端前端，并完成了 NDJSON 事件桥接。本文档说明如何在本地把它跑起来。

---

## 1. 环境准备（一次性）

```bash
cd ~/solvita

# Python 后端
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Node 前端
cd cli
npm install
npm run build
npm link          # 把 `solvita` 注册成全局命令
cd ..
```

检查：

```bash
.venv/bin/python -c "import langgraph; print('python ok')"
which solvita                  # 应输出 …/bin/solvita
ls cli/dist/index.js           # 编译产物应存在
```

---

## 2. 配置 LLM 提供商

`config/models.yaml` 默认配为 OpenAI 兼容端点 + `gpt-4o-mini`：

```yaml
llm:
  provider: "openai_compatible"
  base_url: "https://api.openai.com/v1"
  api_key: ""          # 留空，运行时从环境变量读
  model: "gpt-4o-mini"
```

要换 provider/model：直接改 `base_url` 和 `model` 字段。**永远不要把 api_key 写进 yaml 或 .env 提交进 git**。

---

## 3. 每次运行前

```bash
export SOLVITA_API_KEY='sk-...'                    # 必填
export SOLVITA_BASE_URL='https://api.openai.com/v1'  # 选填，yaml 已兜底
```

key 只活在当前 shell 会话里，关掉窗口就没了。

---

## 4. 运行方式

### 方式 A：`run_solvita.sh`（推荐，自动指向 venv）

```bash
./run_solvita.sh solve examples/problem_input_example.json -n 5 -o my_sol.cpp
```

参数：

| 参数 | 含义 | 默认 |
|---|---|---|
| `solve <file>` | 喂题面 JSON 文件 | — |
| `-o, --output <path>` | 解的 `.cpp` 输出路径 | `solution.cpp` |
| `-n, --max-iterations <N>` | 修复循环上限 | `5` |
| `-p, --python <bin>` | Python 解释器路径 | wrapper 已自动指向 `.venv/bin/python` |

### 方式 B：交互式 TUI

⚠️ 交互模式内部硬编码 `python3`，需要先激活 venv：

```bash
source .venv/bin/activate
solvita        # 不带 solve → 进 Ink TUI，里面选文件或粘题面
```

退出 venv：`deactivate`

### 方式 C：直接调后端（跳过前端）

```bash
.venv/bin/python main.py \
  --input examples/problem_input_example.json \
  --output sol.cpp \
  --max-iterations 5 \
  --stream-events           # 加这个 stdout 输出 NDJSON 事件流
```

裸 `main.py` 还支持 `--model`、`--temperature`、`--config`、`--verbose`、`--problem-description`（直接粘题面文本，不必写 JSON）。

---

## 5. 题面 JSON 格式

```json
{
  "description": "题目正文。\n\n输入格式 / 输出格式 / 约束 都写在这里。",
  "time_limit": 2000,
  "space_limit": 256,
  "public_tests": [
    {"input": "4\n2 7 11 15\n9", "output": "0 1"},
    {"input": "3\n3 2 4\n6", "output": "1 2"}
  ]
}
```

字段说明：
- `description` —— 题目正文，纯文本，建议把输入/输出格式、约束、样例解释都写进去
- `time_limit` —— 毫秒
- `space_limit` —— MB
- `public_tests` —— 至少给 1 组样例，越多越好（agent 会用来评估初版代码）

`examples/problem_input_example.json` 是 LeetCode two-sum 的例子，可以照抄。

---

## 6. 运行时形态

启动后 TUI 实时展示阶段进度：

```
Solvita ▸ examples/problem_input_example.json

✓ Abstracting Problem        hashing, data_structures  conf: 99%
✓ Generating Tests           3 test cases
✓ Planning Strategy
⟳ Generating & Testing Code  iter 2  compiled  tests: 3/4 (75%)
⟳ Adversarial Hack Testing
─────────────────────────────────────────────
```

收尾 Summary 卡片：

```
✓ Success │ 3 iters │ 109 LLM calls │ 247 K + 36 K tokens │ 3/3 (100%)
  Solution saved: ~/solvita/my_sol.cpp
```

阶段：

| 阶段 | 做什么 | 显示细节 |
|---|---|---|
| `abstract_phase` | 抽取标签、估置信度 | `tags, conf: 99%` |
| `testgen_phase` | 生成测试用例 | `N test cases` |
| `solver_skill_plan` | skill-graph 算法规划（可选） | algorithm 名 |
| `codegen_phase` | LLM 写 C++ + 编译 + 跑测试 | `iter k │ compiled │ tests x/y (z%)` |
| `hacker_phase` | 对抗测试找 bug | `n round(s) — all clear` 或 `bug found — looping back` |

`hacker_phase` 找到 bug 时会自动回到 `codegen_phase` 修复，直到 AC 或撞 `max_iterations`。

---

## 7. 输出文件

每次成功运行会落盘 3 个文件：

- `<output>.cpp` —— 最终代码
- `<output>.metadata.json` —— 状态摘要（status / iterations / pass_rate / tests）
- `solvita_run.log` —— 后端 loguru 完整日志（已 gitignored）

---

## 8. 故障排查

| 现象 | 原因 / 修法 |
|---|---|
| `ERROR: SOLVITA_API_KEY is not set` | 没 export key，重做第 3 节 |
| `ModuleNotFoundError: langgraph` | 没用 venv 的 python。用 `run_solvita.sh` 或 `--python .venv/bin/python` |
| `401 Incorrect API key` | key 拼错、失效，或 base_url 跟 key 对不上 |
| `503 No available channel for model X` | provider 不支持那个 model id，改 `config/models.yaml` 的 `model:` |
| stdout 混入非 JSON 行 | 检查后端有没有意外 `print(...)` 不带 `flush=True` 污染 stream 模式 |
| TUI 不刷新 | 没在真终端跑（headless / pipe）。Ink 需要 TTY |
| 跑得慢 | 正常。单题 100+ LLM 调用，含 reasoning 的模型通常 5–10 分钟 |

查后端日志：

```bash
tail -f solvita_run.log
```

---

## 9. 配置进阶

| 文件 | 控制什么 |
|---|---|
| `config/models.yaml` | LLM provider / model / 各角色（code/generator/validator/checker/hacker）的模型重写 / embedding |
| `config/solver_network.yaml` | skill-graph 规划是否启用、ensemble 分支数 |
| `config/trainable_memory.yaml` | trainable memory（Plan / Oracle / Hacker 三套）开关 |
| `config/prompt_template.yaml` | 所有节点的 prompt 模板（abstract / testgen / codegen / hacker / analyst …） |
| `config/tag_whitelist.yaml` | abstract 阶段允许的标签集合 |

---

## 10. 分支说明

```
dev               ← 你正在用的：前端 + 最新后端 + 事件桥
supplement_upload ← 最新后端（无前端）
with_network      ← 后端 backup（落后 supplement_upload 3 commit）
solvita-cli       ← 旧前端 + 旧后端（后端缺很多新东西，不推荐用）
main              ← 早期骨架，仅供参考
```

`dev` 当前 HEAD：

```
634ae19  chore: add run_solvita.sh wrapper, ignore build artifacts
632df8b  config: provide generic OpenAI-compatible defaults
ed2a560  fix: stop --model default overriding yaml-resolved model
0e19a6a  feat: port NDJSON event-streaming bridge from solvita-cli backend
aab2898  merge: add solvita-cli frontend onto latest backend (supplement_upload)
```

---

## 11. 三步速记

```bash
# 1. 进项目 + export key（每个新终端做一次）
cd ~/solvita
export SOLVITA_API_KEY='sk-...'

# 2. 跑
./run_solvita.sh solve examples/problem_input_example.json -n 5 -o sol.cpp

# 3. 看结果
cat sol.cpp
cat sol.metadata.json
```
