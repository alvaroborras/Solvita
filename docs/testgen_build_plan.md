# Test Generation Module (src/testgen) - 详细构建计划

## 一、模块概述

### 功能定位
测试生成模块负责根据问题描述和公开测试用例，智能生成大量高质量的测试用例（目标：20-100个），用于验证生成的C++代码的正确性。

### 核心组件
1. **TestGenerator** - 测试用例生成器（LLM驱动 + 规则辅助）
2. **TestValidator** - 测试用例验证器（约束检查 + 格式验证）

### 输入输出
- **输入**:
  - 解析后的问题结构（来自 `ProblemParser`）
  - 公开测试用例列表（通常2-5个）
  - 问题约束条件
- **输出**:
  - 验证过的测试用例列表（每个包含 `input` 和 `expected_output`）
  - 测试覆盖度元数据

---

## 二、数据结构设计

### 2.1 测试用例数据结构

```python
# 单个测试用例
TestCase = {
    "id": str,                    # 测试用例唯一标识
    "input": str,                 # 输入数据（多行字符串）
    "expected_output": str,       # 期望输出（可选，LLM生成的可能没有）
    "category": str,              # 类别：edge_case, corner_case, random, public
    "description": str,           # 测试用例描述
    "constraints_satisfied": bool, # 是否满足约束
    "metadata": {
        "generated_by": str,      # 生成方法：llm, rule_based
        "complexity": str,        # 复杂度：simple, medium, hard
        "coverage_target": str    # 覆盖目标：min, max, boundary, typical
    }
}
```

### 2.2 问题约束结构

```python
# 从 ProblemParser 接收的约束信息
Constraints = {
    "variables": [
        {
            "name": str,          # 变量名（如 n, m, a[i]）
            "type": str,          # 类型：int, long, string, array
            "min": int/float,     # 最小值
            "max": int/float,     # 最大值
            "length_constraint": dict  # 数组/字符串长度约束
        }
    ],
    "time_limit": int,            # 时间限制（ms）
    "memory_limit": int,          # 内存限制（MB）
    "special_constraints": []     # 特殊约束（如：数组有序、互质等）
}
```

### 2.3 输入格式描述

```python
InputFormat = {
    "pattern": str,               # 输入模式描述
    "lines": [
        {
            "line_number": int,
            "content": str,       # 该行包含的内容描述
            "format": str         # 格式：single_int, space_separated, etc.
        }
    ]
}
```

---

## 三、详细实现计划

### Phase 1: TestValidator 实现（基础设施）

#### 3.1.1 基础验证器实现
**文件**: `src/testgen/validator.py`

**任务分解**:
1. **`__init__()`** - 初始化验证器
   - 加载约束解析规则
   - 初始化正则表达式模式库

2. **`validate_input_format(test_input: str, expected_format: str) -> bool`**
   - 解析 `expected_format` 描述
   - 检查行数是否匹配
   - 验证每行的数据类型和数量
   - 使用正则表达式验证格式

   **实现细节**:
   ```python
   # 支持的格式模式
   - "single_int" -> 单个整数
   - "two_ints" -> 两个空格分隔的整数
   - "array_n_ints" -> n个空格分隔的整数
   - "string_length_n" -> 长度为n的字符串
   ```

3. **`validate_constraints(test: Dict, constraints: Dict) -> bool`**
   - 提取测试输入中的所有变量值
   - 逐个检查约束条件：
     - 数值范围检查（min/max）
     - 数组长度检查
     - 特殊约束检查（如有序性、互质性）
   - 返回布尔值 + 违反的约束列表

   **实现策略**:
   ```python
   # 使用解析器将输入字符串转为变量字典
   # 对每个变量应用相应的约束检查规则
   # 记录所有违反的约束
   ```

4. **`validate(test: Dict, constraints: Dict) -> bool`**
   - 组合调用 `validate_input_format` 和 `validate_constraints`
   - 设置 `test["constraints_satisfied"]` 字段
   - 返回总体验证结果

5. **`filter_invalid_tests(tests: List[Dict], constraints: Dict) -> List[Dict]`**
   - 批量验证测试用例
   - 过滤掉不满足约束的用例
   - 记录过滤统计信息（多少被过滤，原因分布）

**依赖**:
- `src/parser/problem_parser.py` 的约束提取功能
- 标准库：`re`, `typing`

**测试用例**:
```python
# tests/test_testgen.py
def test_validate_input_format()
def test_validate_constraints_numeric()
def test_validate_constraints_array()
def test_filter_invalid_tests()
```

---

### Phase 2: TestGenerator 核心实现

#### 3.2.1 LLM驱动的测试生成

**文件**: `src/testgen/test_generator.py`

**任务分解**:

1. **`__init__(self, llm)`** - 初始化生成器
   - 存储 LLM 实例引用
   - 加载提示词模板
   - 初始化验证器实例
   - 设置默认配置（温度、最大token等）

2. **`generate(problem: Dict, public_tests: List[Dict], num_tests: int = 20) -> List[Dict]`**
   - **主流程**:
     1. 分析公开测试用例，识别模式
     2. 分配测试用例生成策略：
        - 边界情况（edge cases）: 30%
        - 角落情况（corner cases）: 20%
        - 随机情况（random cases）: 50%
     3. 调用各子生成器
     4. 合并所有测试用例
     5. 通过验证器过滤
     6. 如果数量不足，补充随机用例
     7. 返回最终测试集

   **实现细节**:
   ```python
   num_edge = int(num_tests * 0.3)
   num_corner = int(num_tests * 0.2)
   num_random = num_tests - num_edge - num_corner

   edge_cases = self.generate_edge_cases(problem)
   corner_cases = self.generate_corner_cases(problem)
   random_cases = self.generate_random_cases(problem, num_random)

   all_tests = edge_cases + corner_cases + random_cases
   validated_tests = self.validator.filter_invalid_tests(all_tests, problem["constraints"])

   # 去重逻辑
   unique_tests = self._deduplicate_tests(validated_tests)

   # 补充逻辑
   if len(unique_tests) < num_tests:
       additional = self.generate_random_cases(problem, num_tests - len(unique_tests))
       unique_tests.extend(additional)

   return unique_tests[:num_tests]
   ```

3. **`generate_edge_cases(problem: Dict) -> List[Dict]`**
   - **目标**: 生成边界值测试（最小值、最大值、边界附近值）

   **策略**:
   - **规则优先**:
     - 直接根据约束生成：
       - 所有变量取最小值
       - 所有变量取最大值
       - 混合边界（部分最小，部分最大）
   - **LLM辅助**:
     - 提示词包含约束信息
     - 要求生成边界附近的特殊情况

   **提示词模板**:
   ```python
   EDGE_CASE_PROMPT = """
   Generate edge case test inputs for this competitive programming problem:

   Problem: {problem_description}

   Constraints: {constraints}

   Public tests: {public_tests}

   Generate test cases that explore boundary values:
   - Minimum possible values
   - Maximum possible values
   - Values near boundaries (min+1, max-1)

   Return in JSON format:
   [
     {
       "input": "...",
       "description": "All minimum values"
     },
     ...
   ]
   """
   ```

   **实现**:
   ```python
   # 1. 规则生成基础边界用例
   rule_based_edges = self._generate_rule_based_edges(problem["constraints"])

   # 2. LLM生成补充边界用例
   prompt = self._format_edge_case_prompt(problem)
   llm_response = self.llm.generate(prompt, temperature=0.3)
   llm_edges = self._parse_llm_test_output(llm_response)

   # 3. 合并并标记
   all_edges = rule_based_edges + llm_edges
   for test in all_edges:
       test["category"] = "edge_case"
       test["metadata"]["generated_by"] = "rule_based" or "llm"

   return all_edges
   ```

4. **`generate_corner_cases(problem: Dict) -> List[Dict]`**
   - **目标**: 生成特殊角落情况（空输入、单元素、特殊模式）

   **策略**:
   - 识别问题类型特定的角落情况：
     - **数组问题**: 空数组、单元素、全相同元素、严格递增/递减
     - **图问题**: 无边图、完全图、树、环
     - **字符串问题**: 空串、单字符、全相同字符、回文
     - **数学问题**: 0、1、质数、合数

   **提示词模板**:
   ```python
   CORNER_CASE_PROMPT = """
   Generate corner case test inputs for this problem:

   Problem: {problem_description}
   Problem Type: {problem_types}  # 从 ProblemParser 获取

   Generate special cases that often cause bugs:
   - Empty/minimal inputs
   - Uniform/repetitive patterns
   - Special mathematical properties
   - Boundary conditions specific to {problem_types}

   Public tests for reference: {public_tests}

   Return 5-10 corner cases in JSON format.
   """
   ```

   **实现**:
   ```python
   # 基于问题类型调用对应的角落情况生成器
   problem_types = problem.get("types", [])

   corner_cases = []
   if "array" in problem_types or "dp" in problem_types:
       corner_cases.extend(self._generate_array_corners(problem))
   if "graph" in problem_types:
       corner_cases.extend(self._generate_graph_corners(problem))
   if "string" in problem_types:
       corner_cases.extend(self._generate_string_corners(problem))

   # LLM补充通用角落情况
   llm_corners = self._llm_generate_corners(problem)
   corner_cases.extend(llm_corners)

   for test in corner_cases:
       test["category"] = "corner_case"

   return corner_cases
   ```

5. **`generate_random_cases(problem: Dict, num_cases: int) -> List[Dict]`**
   - **目标**: 生成满足约束的随机测试用例

   **策略**:
   - **混合方法**:
     1. 规则随机生成（快速、保证约束）- 70%
     2. LLM随机生成（多样性、覆盖特殊模式）- 30%

   **规则随机生成**:
   ```python
   import random

   def _rule_based_random(constraints: Dict) -> str:
       """根据约束随机生成输入"""
       result_lines = []

       for var in constraints["variables"]:
           if var["type"] == "int":
               value = random.randint(var["min"], var["max"])
               result_lines.append(str(value))
           elif var["type"] == "array":
               length = random.randint(var["length_min"], var["length_max"])
               elements = [random.randint(var["elem_min"], var["elem_max"])
                          for _ in range(length)]
               result_lines.append(f"{length}")
               result_lines.append(" ".join(map(str, elements)))
           # ... 其他类型处理

       return "\n".join(result_lines)
   ```

   **LLM随机生成**:
   ```python
   RANDOM_CASE_PROMPT = """
   Generate {num} diverse random test cases for:

   Problem: {problem_description}
   Constraints: {constraints}
   Public tests: {public_tests}

   Requirements:
   - All inputs must satisfy constraints
   - Cover different input patterns
   - Vary complexity (simple, medium, hard)

   Return in JSON format with inputs only (no outputs needed).
   """
   ```

6. **辅助方法实现**:

   **`_deduplicate_tests(tests: List[Dict]) -> List[Dict]`**
   - 基于输入内容去重
   - 使用哈希或字符串比较

   **`_parse_llm_test_output(response: str) -> List[Dict]`**
   - 解析LLM返回的JSON
   - 处理格式错误和异常
   - 标准化为内部数据结构

   **`_format_edge_case_prompt(problem: Dict) -> str`**
   - 格式化提示词模板
   - 插入问题描述、约束、公开测试

   **`_generate_rule_based_edges(constraints: Dict) -> List[Dict]`**
   - 纯规则生成边界用例
   - 最小值、最大值、边界附近值组合

   **`_generate_array_corners(problem: Dict) -> List[Dict]`**
   - 数组特定角落情况：空、单元素、全相同等

   **`_generate_graph_corners(problem: Dict) -> List[Dict]`**
   - 图特定角落情况：无边、完全图、链等

   **`_generate_string_corners(problem: Dict) -> List[Dict]`**
   - 字符串角落情况：空串、单字符、回文等

---

### Phase 3: Prompt模板优化

**文件**: `src/utils/prompt_templates.py`

**任务**:
1. 扩展现有的 `GENERATE_TESTS` 模板，使其更具体：
   - 明确输出格式要求（JSON schema）
   - 添加few-shot示例
   - 强调约束满足的重要性

2. 添加专用模板：
   ```python
   GENERATE_EDGE_CASES = """..."""
   GENERATE_CORNER_CASES = """..."""
   GENERATE_RANDOM_CASES = """..."""
   VALIDATE_TEST_OUTPUT = """..."""  # 让LLM帮助验证生成的测试
   ```

3. 实现 `format_prompt` 静态方法:
   ```python
   @staticmethod
   def format_prompt(template: str, **kwargs) -> str:
       return template.format(**kwargs)
   ```

---

### Phase 4: 集成和测试

#### 4.1 单元测试

**文件**: `tests/test_testgen.py`

**测试用例**:
```python
import pytest
from src.testgen import TestGenerator, TestValidator
from src.llm import ModelFactory

class TestTestGenerator:
    @pytest.fixture
    def llm(self):
        # Mock LLM or use actual model
        return ModelFactory.create("gpt-4")

    @pytest.fixture
    def generator(self, llm):
        return TestGenerator(llm)

    def test_generate_returns_correct_number(self, generator):
        """测试生成指定数量的测试用例"""
        problem = {...}  # Mock problem
        public_tests = [...]

        tests = generator.generate(problem, public_tests, num_tests=20)
        assert len(tests) == 20

    def test_edge_cases_satisfy_constraints(self, generator):
        """测试边界用例满足约束"""
        problem = {
            "constraints": {
                "variables": [{"name": "n", "min": 1, "max": 100}]
            }
        }

        edges = generator.generate_edge_cases(problem)
        validator = TestValidator()

        for test in edges:
            assert validator.validate_constraints(test, problem["constraints"])

    def test_deduplication(self, generator):
        """测试去重功能"""
        tests = [
            {"input": "5\n1 2 3 4 5"},
            {"input": "5\n1 2 3 4 5"},  # 重复
            {"input": "3\n1 2 3"}
        ]
        unique = generator._deduplicate_tests(tests)
        assert len(unique) == 2

    def test_random_cases_vary(self, generator):
        """测试随机用例的多样性"""
        problem = {...}
        cases = generator.generate_random_cases(problem, 10)

        # 验证不是所有用例都相同
        unique_inputs = set(test["input"] for test in cases)
        assert len(unique_inputs) > 5  # 至少一半不同

class TestTestValidator:
    def test_validate_input_format_single_int(self):
        """测试单整数格式验证"""
        validator = TestValidator()
        assert validator.validate_input_format("42", "single_int")
        assert not validator.validate_input_format("42 43", "single_int")

    def test_validate_constraints_range(self):
        """测试数值范围约束"""
        validator = TestValidator()
        test = {"input": "5"}
        constraints = {
            "variables": [{"name": "n", "type": "int", "min": 1, "max": 10}]
        }
        assert validator.validate_constraints(test, constraints)

        test_invalid = {"input": "15"}
        assert not validator.validate_constraints(test_invalid, constraints)

    def test_filter_invalid_tests(self):
        """测试批量过滤"""
        validator = TestValidator()
        tests = [
            {"input": "5"},    # 有效
            {"input": "15"},   # 无效（超出范围）
            {"input": "3"}     # 有效
        ]
        constraints = {
            "variables": [{"name": "n", "type": "int", "min": 1, "max": 10}]
        }

        filtered = validator.filter_invalid_tests(tests, constraints)
        assert len(filtered) == 2
```

#### 4.2 集成测试

**文件**: `tests/integration/test_testgen_integration.py`

```python
def test_full_pipeline():
    """测试完整的测试生成流程"""
    # 1. 解析问题
    from src.parser import ProblemParser
    parser = ProblemParser()
    problem = parser.parse({
        "description": "Given array, find two sum...",
        "public_tests": [{"input": "...", "output": "..."}]
    })

    # 2. 生成测试
    from src.llm import ModelFactory
    from src.testgen import TestGenerator

    llm = ModelFactory.create("gpt-4")
    generator = TestGenerator(llm)

    tests = generator.generate(problem, problem["public_tests"], num_tests=30)

    # 3. 验证
    assert len(tests) == 30
    assert all("input" in test for test in tests)
    assert all("category" in test for test in tests)

    # 4. 统计分布
    categories = [test["category"] for test in tests]
    assert "edge_case" in categories
    assert "corner_case" in categories
    assert "random" in categories
```

---

## 四、实现优先级

### P0 - 核心功能（第1-2周）
1. ✅ `TestValidator.validate_input_format()` - 基础格式验证
2. ✅ `TestValidator.validate_constraints()` - 约束检查
3. ✅ `TestGenerator.__init__()` - 初始化
4. ✅ `TestGenerator.generate_random_cases()` - 规则随机生成
5. ✅ `TestGenerator.generate()` - 主流程

### P1 - 增强功能（第3周）
6. ✅ `TestGenerator.generate_edge_cases()` - 边界用例（规则为主）
7. ✅ `TestGenerator.generate_corner_cases()` - 角落用例（基础实现）
8. ✅ Prompt模板优化
9. ✅ 单元测试覆盖

### P2 - 高级功能（第4周）
10. ✅ LLM驱动的边界/角落用例生成
11. ✅ 问题类型特定的生成器（数组、图、字符串）
12. ✅ 测试用例质量评估（覆盖度、多样性）
13. ✅ 集成测试和性能优化

---

## 五、关键技术挑战

### 5.1 约束提取准确性
**挑战**: 从自然语言描述中准确提取约束
**解决方案**:
- 结合LLM理解 + 正则表达式模式匹配
- 人工标注一批训练数据，建立约束提取规则库
- 对于复杂约束，采用保守策略（放宽而非收紧）

### 5.2 LLM生成测试的有效性
**挑战**: LLM可能生成不满足约束或格式错误的测试
**解决方案**:
- 多轮生成 + 严格验证过滤
- 使用温度较低的设置（0.2-0.4）提高稳定性
- 提供详细的few-shot示例
- 对LLM生成结果进行后处理修正

### 5.3 测试覆盖度
**挑战**: 确保生成的测试充分覆盖各种情况
**解决方案**:
- 分类生成策略（边界30% + 角落20% + 随机50%）
- 记录已覆盖的模式，动态调整生成策略
- 引入覆盖度指标（如：边界值覆盖率、分支覆盖率）

### 5.4 性能优化
**挑战**: 生成大量测试用例可能耗时较长
**解决方案**:
- 规则生成为主（快速），LLM生成为辅（质量）
- 并行调用LLM API（对于多个独立的生成请求）
- 缓存常见问题类型的测试模板
- 增量生成（先生成10个，不够再补充）

---

## 六、依赖项

### 内部依赖
- `src/parser/problem_parser.py` - 必须先实现约束提取功能
- `src/llm/base_model.py` - LLM接口
- `src/utils/prompt_templates.py` - 提示词模板

### 外部依赖
- `openai` / `anthropic` - LLM API
- `pydantic` - 数据验证
- `pytest` - 单元测试

---

## 七、成功指标

### 量化指标
1. **生成成功率**: ≥95% 的生成请求成功完成
2. **约束满足率**: ≥98% 的生成测试满足所有约束
3. **去重效率**: 去重后保留 ≥80% 的生成测试（说明多样性好）
4. **生成速度**: 生成20个测试用例 ≤30秒（包括LLM调用）

### 质量指标
1. **覆盖度**:
   - 边界值覆盖率 100%（所有min/max组合）
   - 角落情况覆盖率 ≥80%（空、单元素、特殊模式等）
2. **多样性**:
   - 输入模式多样性（通过聚类分析）
   - 难度分布均衡（简单、中等、困难）

### 功能指标
1. 支持所有常见问题类型（数组、图、字符串、数学、DP）
2. 支持复杂约束（嵌套数组、多变量关联等）
3. 错误处理健壮性（LLM失败、格式错误等）

---

## 八、风险和缓解

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| LLM生成质量不稳定 | 高 | 高 | 增加规则生成占比，多轮验证过滤 |
| 约束提取不准确 | 中 | 高 | 保守策略，人工审核关键约束 |
| 生成速度过慢 | 中 | 中 | 并行化，缓存，规则优先 |
| 测试覆盖度不足 | 低 | 中 | 分类生成策略，覆盖度监控 |

---

## 九、下一步行动

### 立即开始（本周）
1. [ ] 实现 `TestValidator` 基础功能（格式验证 + 简单约束检查）
2. [ ] 实现 `TestGenerator` 规则随机生成
3. [ ] 编写核心单元测试

### 下周
4. [ ] 实现边界/角落用例生成（规则版本）
5. [ ] 集成LLM调用
6. [ ] 优化提示词模板

### 后续
7. [ ] 问题类型特定生成器
8. [ ] 覆盖度评估和质量监控
9. [ ] 性能优化和集成测试

---

## 十、参考资料

- **Competitive Programming测试生成**: [CP Test Generator Research](https://example.com)
- **约束求解**: Z3 Solver, SMT理论
- **LLM Prompt Engineering**: OpenAI Best Practices
- **代码测试覆盖**: pytest-cov, coverage.py
