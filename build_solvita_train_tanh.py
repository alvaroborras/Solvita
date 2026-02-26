"""
构建 solvita-train 数据集（tanh 副本）

变更内容（相对原脚本）：
1. 新增 detect_lang() — 基于代码文本检测语言（cpp/python3/python2/java/other）
2. _normalize_cc_solutions：unknown(0) 语言改为代码文本检测，不再直接丢弃
3. extract_fields_from_apps：增加 filter_lang 参数，用 detect_lang 过滤 APPS 解答
4. 保留 test_case 字段（含公有测试用例，服务于训练脚本中的对拍验证）
5. 输出文件名改为 solvita_train_tanh.jsonl

训练集来源（按顺序）：
1. code-contests (train split)
2. code-contests-plus 1x（从本地缓存 parquet 加载）
3. APPS (train split)

过滤条件：
1. 不在 APPS(test) 和 code-contest(test) 中
2. 不在已有的 solvita-data 中

特殊规则：
- codewars, hackerearth: 可以直接放入
- leetcode, hackerrank: 只需与 APPS(test) 比较
- aizu: 只需与 solvita-data 比较
- atcoder: 直接不放入
"""

import os

# ⚠️ 必须在导入 datasets 之前设置环境变量！
# 在脚本开头设置 HF 缓存目录到大盘，避免磁盘空间不足
# 这样无论从哪个终端运行，都会使用大盘作为缓存目录
hf_cache_base = "<workspace>/hf_cache"
os.environ["HF_HOME"] = hf_cache_base
os.environ["HF_DATASETS_CACHE"] = os.path.join(hf_cache_base, "datasets")
os.makedirs(os.environ["HF_DATASETS_CACHE"], exist_ok=True)
print(f"HF cache directory set to: {os.environ['HF_DATASETS_CACHE']}")

# 现在才导入 datasets，这样它会使用上面设置的缓存目录
import json
import re
import argparse
import shutil
import time
import urllib.request
from pathlib import Path
from typing import Dict, Set, List, Any, Optional, Tuple
from urllib.parse import urlparse
from collections import defaultdict
from datasets import load_dataset, DatasetDict, Dataset
import pyarrow.parquet as pq

# 路径配置
SOLVITA_DATA_DIR = Path("<workspace>/duture/solvita/data")
SOLVITA_DATA_PROBLEM_DIR = SOLVITA_DATA_DIR / "problem"  # 已存在的 solvita-data
OUTPUT_DIR = SOLVITA_DATA_DIR / "solvita_train"
OUTPUT_DIR.mkdir(exist_ok=True, parents=True)


# 可用的源数据集
DATASET_NAMES = ["code-contests-plus", "code-contests", "apps"]

# Code-Contests source 映射
CC_SOURCE_MAP = {
    1: "codechef",
    2: "codeforces",
    3: "hackerearth",
    4: "codejam",
    5: "atcoder",
    6: "aizu",
}

# ---------- Tags 获取（Codeforces / Codewars / LeetCode API）-----------
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import leetcode_utils
import codechef_utils
_CF_TAGS_CACHE: Optional[Dict[Tuple[int, str], List[str]]] = None


def _fetch_cf_tags_cache() -> Dict[Tuple[int, str], List[str]]:
    """获取 Codeforces 题目 tags 映射，仅请求一次并缓存。限速 1 req/2s 已满足。"""
    global _CF_TAGS_CACHE
    if _CF_TAGS_CACHE is not None:
        return _CF_TAGS_CACHE
    cache: Dict[Tuple[int, str], List[str]] = {}
    try:
        req = urllib.request.Request(
            "https://codeforces.com/api/problemset.problems",
            headers={"User-Agent": "solvita-train-builder"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        if data.get("status") != "OK":
            return cache
        for p in data.get("result", {}).get("problems", []):
            cid = p.get("contestId")
            idx = p.get("index", "")
            tags = p.get("tags", [])
            if cid is not None and isinstance(tags, list):
                cache[(int(cid), str(idx))] = [str(t) for t in tags]
        _CF_TAGS_CACHE = cache
        print(f"  [Tags] Codeforces problemset cached: {len(cache)} problems")
    except Exception as e:
        print(f"  [Tags] Failed to fetch Codeforces problemset: {e}")
    return cache


def get_tags_for_cc(problem: Dict[str, Any]) -> List[str]:
    """从 Code-Contests 题目提取 tags（cf_tags 字段）"""
    raw = problem.get("cf_tags")
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(t) for t in raw if t]
    if isinstance(raw, dict) and "input" in raw:
        return [str(t) for t in raw["input"] if t]
    return []


def get_tags_for_ccplus(problem: Dict[str, Any], problem_id: str) -> List[str]:
    """从 Code-Contests-Plus 提取 tags，对 codeforces、codechef 通过 API 查询"""
    source = (problem.get("source") or "").lower()
    if source == "codeforces":
        # id 格式如 802_E，反推 URL: problem/802/E
        raw_id = problem.get("id") or ""
        if not raw_id:
            prefix = "codeforces_"
            if problem_id.lower().startswith(prefix):
                raw_id = problem_id[len(prefix):].replace("-", "_")
        if not raw_id:
            return []
        parts = raw_id.replace("-", "_").split("_")
        if len(parts) < 2:
            return []
        try:
            contest_id = int(parts[0])
            index = (parts[1] or "A").upper()
        except (ValueError, IndexError):
            return []
        cache = _fetch_cf_tags_cache()
        return cache.get((contest_id, index), [])
    if source == "codechef":
        raw_id = problem.get("id") or ""
        if not raw_id and problem_id.lower().startswith("codechef_"):
            raw_id = problem_id[len("codechef_"):].replace("-", "_")
        if raw_id:
            return codechef_utils.get_codechef_tags(raw_id)
        return []
    return []


def get_tags_for_apps(
    url: str, parsed: Optional[Tuple[str, str]], problem_id: str
) -> List[str]:
    """从 APPS 题目提取 tags，仅对 codeforces、codewars、leetcode、codechef 通过 API 查询"""
    if not parsed:
        return []
    source, identifier = parsed
    source_lower = source.lower()
    if source_lower == "codeforces":
        # identifier 如 "1036_B" 或 "1036"
        parts = identifier.replace("-", "_").split("_")
        if len(parts) < 2:
            return []
        try:
            contest_id = int(parts[0])
            index = (parts[1] or "A").upper()
        except (ValueError, IndexError):
            return []
        cache = _fetch_cf_tags_cache()
        return cache.get((contest_id, index), [])
    if source_lower == "codewars":
        # identifier 为 kata id/slug，请求 Codewars API
        try:
            time.sleep(1.0)  # 避免 429
            enc = urllib.parse.quote(identifier, safe="")
            req = urllib.request.Request(
                f"https://www.codewars.com/api/v1/code-challenges/{enc}",
                headers={"User-Agent": "solvita-train-builder"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            tags = data.get("tags", [])
            return [str(t) for t in tags] if isinstance(tags, list) else []
        except Exception:
            return []
    if source_lower == "leetcode":
        return leetcode_utils.get_leetcode_tags_from_url(url)
    if source_lower == "codechef":
        # 格式: https://www.codechef.com/[比赛代码]/problems/[题目代码] 或 .../problems/[题目代码]
        contest_code, problem_code = codechef_utils.parse_codechef_url(url)
        if not problem_code:
            return []
        return codechef_utils.get_codechef_tags(problem_code, contest_code=contest_code or "PRACTICE")
    return []


def parse_apps_url(url: str) -> Optional[Tuple[str, str]]:
    """
    从 APPS 的 URL 中解析 source 和 identifier
    
    Returns:
        (source, identifier) 或 None
    """
    if not url:
        return None
    
    url_lower = url.lower()
    
    # Codeforces: https://codeforces.com/problemset/problem/1036/B
    if "codeforces.com/problemset/problem" in url_lower:
        match = re.search(r'/problem/(\d+)([A-Z]?)', url)
        if match:
            contest_id = match.group(1)
            problem_id = match.group(2) or ""
            # 如果有 problem_id，格式为 contest_id_problem_id，否则只有 contest_id
            identifier = f"{contest_id}_{problem_id}" if problem_id else contest_id
            return ("codeforces", identifier)
    
    # CodeChef: https://www.codechef.com/problems/INVYCNT
    elif "codechef.com/problems" in url_lower:
        match = re.search(r'/problems/([^/]+)', url)
        if match:
            return ("codechef", match.group(1).lower())
    
    # LeetCode: https://leetcode.com/problems/get-watched-videos-by-your-friends/
    elif "leetcode.com/problems" in url_lower:
        match = re.search(r'/problems/([^/]+)', url)
        if match:
            return ("leetcode", match.group(1))
    
    # Codewars: https://www.codewars.com/kata/538948d4daea7dc4d200023f
    elif "codewars.com/kata" in url_lower:
        match = re.search(r'/kata/([^/]+)', url)
        if match:
            return ("codewars", match.group(1))
    
    # HackerRank: https://www.hackerrank.com/challenges/validating-named-email-addresses/problem
    elif "hackerrank.com/challenges" in url_lower:
        match = re.search(r'/challenges/([^/]+)', url)
        if match:
            return ("hackerrank", match.group(1))
    
    # Kattis: https://open.kattis.com/problems/100meterdash
    elif "open.kattis.com/problems" in url_lower or "kattis.com/problems" in url_lower:
        match = re.search(r'/problems/([^/]+)', url)
        if match:
            return ("kattis", match.group(1))
    
    # HackerEarth: 可能出现在其他格式中
    elif "hackerearth.com" in url_lower:
        match = re.search(r'/(?:problems|challenges)/([^/]+)', url_lower)
        if match:
            return ("hackerearth", match.group(1))
    
    return None


def extract_codeforces_id_from_name(name: str) -> Optional[str]:
    """从 codeforces 的 name 中提取 ID，如 '709_E. Centroids' -> '709_E'"""
    if not name:
        return None
    match = re.match(r'^(\d+_[A-Z])', name)
    if match:
        return match.group(1).lower()
    return None


def extract_aizu_id_from_name(name: str) -> Optional[str]:
    """从 aizu 的 name 中提取 ID，如 'p02445 Swap' -> 'p02445'"""
    if not name:
        return None
    match = re.match(r'^(p\d+)', name, re.IGNORECASE)
    if match:
        return match.group(1).lower()
    return None


def generate_id_from_apps(problem: Dict[str, Any]) -> Optional[str]:
    """从 APPS 题目生成统一 ID"""
    url = problem.get("url", "")
    parsed = parse_apps_url(url)
    if not parsed:
        return None
    
    source, identifier = parsed
    return f"{source}_{identifier}".lower()


def generate_id_from_ccplus(problem: Dict[str, Any]) -> Optional[str]:
    """从 code-contests-plus 题目生成统一 ID"""
    source = problem.get("source", "")
    if not source:
        return None
    
    source_lower = source.lower()
    
    # 优先使用 id（如果存在且不为空）
    problem_id = problem.get("id")
    if problem_id:
        # 如果 id 存在，直接使用
        return f"{source_lower}_{problem_id}".lower()
    
    # 否则使用 name
    name = problem.get("name", "")
    if name:
        # 根据 source 类型提取
        if source_lower == "codeforces":
            extracted = extract_codeforces_id_from_name(name)
            if extracted:
                return f"{source_lower}_{extracted}".lower()
        elif source_lower == "aizu":
            extracted = extract_aizu_id_from_name(name)
            if extracted:
                return f"{source_lower}_{extracted}".lower()
        
        # 其他情况直接使用 name（小写）
        safe_name = re.sub(r'[^a-z0-9_-]+', '_', name.lower()).strip('_')
        return f"{source_lower}_{safe_name}"
    
    return None


def generate_id_from_cc(problem: Dict[str, Any]) -> Optional[str]:
    """从 code-contests 题目生成统一 ID"""
    source_int = problem.get("source")
    if source_int is None:
        return None
    
    source = CC_SOURCE_MAP.get(source_int, "unknown")
    if source == "unknown":
        return None
    
    name = problem.get("name", "")
    if not name:
        return None
    
    # 根据 source 类型提取 identifier
    identifier = None
    
    if source == "codeforces":
        identifier = extract_codeforces_id_from_name(name)
    elif source == "aizu":
        identifier = extract_aizu_id_from_name(name)
    elif source in ["codechef", "hackerearth"]:
        # 直接使用 name（小写）
        identifier = name.lower()
    elif source == "atcoder":
        # atcoder 不处理
        return None
    
    if identifier:
        return f"{source}_{identifier}".lower()
    
    # 兜底：使用清理后的 name
    safe_name = re.sub(r'[^a-z0-9_-]+', '_', name.lower()).strip('_')
    return f"{source}_{safe_name}"


def load_existing_solvita_data_ids() -> Set[str]:
    """加载已存在的 solvita-data 题目 ID 集合"""
    existing_ids: Set[str] = set()
    
    if not SOLVITA_DATA_PROBLEM_DIR.exists():
        print(f"Warning: solvita-data directory not found: {SOLVITA_DATA_PROBLEM_DIR}")
        return existing_ids
    
    for json_file in SOLVITA_DATA_PROBLEM_DIR.glob("*.json"):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                metadata = data.get("_metadata", {})
                
                # 尝试从 metadata 中提取 ID
                # 可能的字段：source, problem_id, name, id
                source = metadata.get("source", "").lower()
                problem_id = metadata.get("problem_id") or metadata.get("id") or metadata.get("name")
                
                if source and problem_id:
                    # 构建统一格式的 ID
                    if isinstance(problem_id, str):
                        safe_id = re.sub(r'[^a-z0-9_-]+', '_', str(problem_id).lower()).strip('_')
                        existing_ids.add(f"{source}_{safe_id}")
                    else:
                        existing_ids.add(f"{source}_{problem_id}")
                
                # 也可以从文件名提取
                stem = json_file.stem
                if "_" in stem:
                    existing_ids.add(stem.lower())
        except Exception as e:
            print(f"Warning: Failed to load {json_file}: {e}")
    
    print(f"Loaded {len(existing_ids)} existing problem IDs from solvita-data")
    return existing_ids


def build_test_set_ids(datasets: Dict, debug: bool = False) -> Tuple[Set[str], Set[str]]:
    """
    构建测试集 ID 集合
    
    Returns:
        (apps_test_ids, cc_test_ids)
    """
    apps_test_ids: Set[str] = set()
    cc_test_ids: Set[str] = set()
    
    # APPS test
    print("Building APPS test IDs...")
    apps_test = datasets["apps"]["test"]
    total_apps_test = len(apps_test)
    failed_apps = 0
    for idx, problem in enumerate(apps_test):
        if debug and (idx + 1) % 1000 == 0:
            print(f"  Progress: {idx + 1}/{total_apps_test} processed")
        pid = generate_id_from_apps(problem)
        if pid:
            apps_test_ids.add(pid)
        else:
            failed_apps += 1
    print(f"  Found {len(apps_test_ids)} APPS test problems")
    if debug and failed_apps > 0:
        print(f"  Failed to generate ID for {failed_apps} problems")
    
    # CodeContests test
    print("Building CodeContests test IDs...")
    cc_test = datasets["code_contests"]["test"]
    total_cc_test = len(cc_test)
    failed_cc = 0
    for idx, problem in enumerate(cc_test):
        if debug and (idx + 1) % 1000 == 0:
            print(f"  Progress: {idx + 1}/{total_cc_test} processed")
        pid = generate_id_from_cc(problem)
        if pid:
            cc_test_ids.add(pid)
        else:
            failed_cc += 1
    print(f"  Found {len(cc_test_ids)} CodeContests test problems")
    if debug and failed_cc > 0:
        print(f"  Failed to generate ID for {failed_cc} problems")
    
    return apps_test_ids, cc_test_ids


def should_include_problem(
    problem_id: str,
    source: str,
    apps_test_ids: Set[str],
    cc_test_ids: Set[str],
    solvita_data_ids: Set[str]
) -> bool:
    """
    判断是否应该包含该题目
    
    特殊规则：
    - codewars, hackerearth: 可以直接放入
    - leetcode, hackerrank: 只需与 APPS(test) 比较
    - aizu: 只需与 solvita-data 比较
    - atcoder: 直接不放入
    """
    source_lower = source.lower()
    
    # atcoder 直接排除
    if source_lower == "atcoder":
        return False
    
    # codewars, hackerearth 可以直接放入
    if source_lower in ["codewars", "hackerearth"]:
        return True
    
    # leetcode, hackerrank 只需与 APPS(test) 比较
    if source_lower in ["leetcode", "hackerrank"]:
        return problem_id not in apps_test_ids
    
    # aizu 只需与 solvita-data 比较
    if source_lower == "aizu":
        return problem_id not in solvita_data_ids
    
    # 其他：需要同时满足不在测试集和 solvita-data 中
    return problem_id not in apps_test_ids and problem_id not in cc_test_ids and problem_id not in solvita_data_ids


def extract_fields_from_apps(
    problem: Dict[str, Any],
    max_correct_solutions: Optional[int] = None,
    max_incorrect_solutions: Optional[int] = None,
    filter_lang: bool = True,
) -> Dict[str, Any]:
    """
    从 APPS 题目提取字段

    Args:
        problem: 题目数据
        max_correct_solutions: 最大正确解数量限制（None 表示不限制）
        max_incorrect_solutions: 最大错误解数量限制（None 表示不限制，APPS 没有错误解）
        filter_lang: 是否过滤语言（True 时仅保留 cpp/python3）
    """
    result = {
        "description": problem.get("question", ""),
        "correct_solution": None,
        "incorrect_solution": None,
    }

    # 提取 correct_solution，统一为 CC+ 格式 [{"code":str},...]
    solution = problem.get("solutions")
    if solution:
        if not isinstance(solution, list):
            solution = [solution]
        if filter_lang:
            solution = [
                s for s in solution
                if detect_lang(s if isinstance(s, str) else (s.get("code", "") if isinstance(s, dict) else ""))
                in ("cpp", "python3")
            ]
        if max_correct_solutions:
            solution = solution[:max_correct_solutions]
        result["correct_solution"] = _to_unified_solution(solution)

    # 提取 test_case：APPS 的 input_output 字段
    raw_io = problem.get("input_output")
    if raw_io:
        if isinstance(raw_io, str):
            try:
                raw_io = json.loads(raw_io)
            except Exception:
                raw_io = None
        if isinstance(raw_io, dict):
            inputs = raw_io.get("inputs", raw_io.get("input", []))
            outputs = raw_io.get("outputs", raw_io.get("output", []))
            if not isinstance(inputs, list):
                inputs = [str(inputs)] if inputs else []
            if not isinstance(outputs, list):
                outputs = [str(outputs)] if outputs else []
            n = max(len(inputs), len(outputs))
            inputs = (list(inputs) + [""] * n)[:n]
            outputs = (list(outputs) + [""] * n)[:n]
            tc_list = [{"input": str(i), "output": str(o)} for i, o in zip(inputs, outputs)]
            if tc_list:
                result["test_case"] = tc_list

    return result


def _to_unified_test_case(raw: Any) -> Optional[List[Dict[str, str]]]:
    """
    统一为 CC 格式：list of {input, output}。
    支持：list of {input,output}、dict {input:[], output:[]}、dict {inputs:[], outputs:[]}
    """
    if raw is None:
        return None
    result = []
    if isinstance(raw, list):
        for t in raw:
            if isinstance(t, dict):
                result.append({"input": t.get("input", t.get("inputs", "")), "output": t.get("output", t.get("outputs", ""))})
    elif isinstance(raw, dict):
        inputs = raw.get("input", raw.get("inputs", []))
        outputs = raw.get("output", raw.get("outputs", []))
        if not isinstance(inputs, list):
            inputs = [str(inputs)] if inputs else []
        if not isinstance(outputs, list):
            outputs = [str(outputs)] if outputs else []
        n = max(len(inputs), len(outputs))
        inputs = (list(inputs) + [""] * n)[:n]
        outputs = (list(outputs) + [""] * n)[:n]
        result = [{"input": i, "output": o} for i, o in zip(inputs, outputs)]
    return result if result else None


def _to_unified_solution(raw: Any) -> Optional[List[Dict[str, str]]]:
    """
    统一为 CC+ 格式：list of {code: str}。
    支持：list of str、list of {code:str}、单个 str
    """
    if raw is None:
        return None
    result = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                code = item.get("code", "")
                if code:
                    result.append({"code": code})
            elif isinstance(item, str):
                result.append({"code": item})
    elif isinstance(raw, str):
        result = [{"code": raw}]
    return result if result else None


def _normalize_cc_tests(tests: Any) -> List[Dict[str, str]]:
    """
    将 code-contests 的 test 格式转为 list of {input, output}。
    支持两种格式：
    - list: [{input, output}, ...]
    - dict: {input: [str, ...], output: [str, ...]}（HuggingFace 原始格式）
    """
    if tests is None:
        return []
    if isinstance(tests, list):
        result = []
        for t in tests:
            if isinstance(t, dict):
                result.append({"input": t.get("input", ""), "output": t.get("output", "")})
        return result
    if isinstance(tests, dict):
        inputs = tests.get("input", [])
        outputs = tests.get("output", [])
        if not isinstance(inputs, list):
            inputs = [str(inputs)] if inputs else []
        if not isinstance(outputs, list):
            outputs = [str(outputs)] if outputs else []
        n = max(len(inputs), len(outputs))
        inputs = (list(inputs) + [""] * n)[:n]
        outputs = (list(outputs) + [""] * n)[:n]
        return [{"input": inp, "output": out} for inp, out in zip(inputs, outputs)]
    return []


# code-contests 语言标识: 0=unknown, 1=Python2, 2=CPP, 3=Python3, 4=Java
CC_LANG_UNKNOWN = 0
CC_LANG_CPP = 2
CC_LANG_PYTHON3 = 3
CC_ALLOWED_LANGS = {CC_LANG_CPP, CC_LANG_PYTHON3}


def detect_lang(code: str) -> str:
    """基于代码文本特征检测语言，用于 unknown(0) 和 APPS 解答的语言判断。

    Returns:
        'cpp' | 'python3' | 'python2' | 'java' | 'other'
    """
    if not code or not code.strip():
        return "other"
    # C++ 特征：以 #include 或 int main 或 cout/cin 为准
    if "#include" in code or "int main" in code or "cout" in code or "cin >>" in code:
        return "cpp"
    # Java 特征
    if "public class" in code or "System.out" in code or "import java." in code:
        return "java"
    # Python 2 特征：raw_input 或 不带括号的 print
    if "raw_input(" in code:
        return "python2"
    if "print " in code and "print(" not in code and "print >>" not in code:
        return "python2"
    # Python 3 特征
    if "print(" in code or "input(" in code or "def " in code or "import " in code:
        return "python3"
    return "other"


def _normalize_cc_solutions(solutions: Any, filter_cc_lang: bool = True) -> List[str]:
    """
    将 code-contests 的 solutions 格式转为 list of code strings。
    当 filter_cc_lang=True 时，仅保留 language 为 2(CPP) 和 3(Python3) 的 solution。
    支持格式：dict: {language: [int, ...], solution: [code_str, ...]}（一一对应）
    """
    if solutions is None:
        return []
    if isinstance(solutions, list):
        return [s for s in solutions if isinstance(s, str)]
    if isinstance(solutions, dict):
        langs = solutions.get("language", [])
        sols = solutions.get("solution", solutions.get("solutions", []))
        if not isinstance(langs, list):
            langs = [langs] if langs is not None else []
        if not isinstance(sols, list):
            sols = [sols] if isinstance(sols, str) else []
        result = []
        for lang, code in zip(langs, sols):
            if not isinstance(code, str):
                continue
            if filter_cc_lang:
                if lang in CC_ALLOWED_LANGS:
                    pass  # C++ 或 Python3，直接保留
                elif lang == CC_LANG_UNKNOWN:
                    # language=unknown：通过代码文本检测，只保留 cpp/python3
                    if detect_lang(code) not in ("cpp", "python3"):
                        continue
                else:
                    # Python2(1) / Java(4) 等，直接丢弃
                    continue
            result.append(code)
        return result
    return []


def extract_fields_from_cc(
    problem: Dict[str, Any],
    max_correct_solutions: Optional[int] = None,
     max_incorrect_solutions: Optional[int] = None,
    filter_cc_lang: bool = True
) -> Dict[str, Any]:
    """
    从 code-contests 题目提取字段
    
    Args:
        problem: 题目数据
        max_correct_solutions: 最大正确解数量限制（None 表示不限制）
        max_incorrect_solutions: 最大错误解数量限制（None 表示不限制）
    """
    result = {
        "description": problem.get("description", ""),
        "test_case": None,
        "correct_solution": None,
        "incorrect_solution": None,
    }
    
    # 提取 test_case，统一为 CC 格式 [{"input","output"},...]
    public_tests = _normalize_cc_tests(problem.get("public_tests"))
    generated_tests = _normalize_cc_tests(problem.get("generated_tests"))
    all_tests = public_tests + generated_tests
    result["test_case"] = all_tests if all_tests else None
    
    # 提取 correct_solution，统一为 CC+ 格式 [{"code":str},...]
    solutions = _normalize_cc_solutions(problem.get("solutions"), filter_cc_lang=filter_cc_lang)
    if solutions:
        if max_correct_solutions and len(solutions) > max_correct_solutions:
            solutions = solutions[:max_correct_solutions]
        result["correct_solution"] = _to_unified_solution(solutions)
    
    # 提取 incorrect_solution，统一为 CC+ 格式
    incorrect_solutions = _normalize_cc_solutions(problem.get("incorrect_solutions"), filter_cc_lang=filter_cc_lang)
    if incorrect_solutions:
        if max_incorrect_solutions and len(incorrect_solutions) > max_incorrect_solutions:
            incorrect_solutions = incorrect_solutions[:max_incorrect_solutions]
        result["incorrect_solution"] = _to_unified_solution(incorrect_solutions)
    
    return result


def _ccplus_1x_item_to_dict(item: Any) -> Optional[Dict]:
    """将 parquet struct/list 元素转为 dict"""
    if item is None:
        return None
    if isinstance(item, dict):
        return item
    if hasattr(item, "_asdict"):
        return item._asdict()
    if hasattr(item, "__iter__") and not isinstance(item, (str, bytes)):
        try:
            return dict(item)
        except (TypeError, ValueError):
            pass
    return None


def extract_fields_from_ccplus(
    problem: Dict[str, Any],
    max_correct_solutions: Optional[int] = None,
    max_incorrect_solutions: Optional[int] = None
) -> Dict[str, Any]:
    """
    从 code-contests-plus 1x 题目提取字段
    
    ccplus_1x 格式：
    - correct_submissions / incorrect_submissions: list of {code, language}
    - test_cases: list of {input, output}
    """
    result = {
        "description": problem.get("description", ""),
        "test_case": None,
        "correct_solution": None,
        "incorrect_solution": None,
    }

    # 提取 test_case，统一为 CC 格式 [{"input","output"},...]
    # ccplus_1x 每个元素为 {input, output}，支持 struct/dict 等
    raw_tc = problem.get("test_cases")
    if raw_tc is not None:
        tc_list = list(raw_tc) if not isinstance(raw_tc, list) else raw_tc
        if tc_list:
            unified = []
            for t in tc_list:
                d = _ccplus_1x_item_to_dict(t)
                if d is None:
                    continue
                inp = d.get("input", d.get("inputs", ""))
                out = d.get("output", d.get("outputs", ""))
                if inp is None:
                    inp = ""
                if out is None:
                    out = ""
                unified.append({"input": str(inp), "output": str(out)})
            if unified:
                result["test_case"] = unified

    # 提取 correct_solution，统一为 CC+ 格式 [{"code":str},...]
    correct_submissions = problem.get("correct_submissions", [])
    if correct_submissions:
        subs = []
        for item in correct_submissions:
            d = _ccplus_1x_item_to_dict(item)
            if d and d.get("code"):
                subs.append({"code": d["code"]})
        if subs:
            if max_correct_solutions and len(subs) > max_correct_solutions:
                subs = subs[:max_correct_solutions]
            result["correct_solution"] = subs

    # 提取 incorrect_solution，统一为 CC+ 格式
    incorrect_submissions = problem.get("incorrect_submissions", [])
    if incorrect_submissions:
        subs = []
        for item in incorrect_submissions:
            d = _ccplus_1x_item_to_dict(item)
            if d and d.get("code"):
                subs.append({"code": d["code"]})
        if subs:
            if max_incorrect_solutions and len(subs) > max_incorrect_solutions:
                subs = subs[:max_incorrect_solutions]
            result["incorrect_solution"] = subs

    return result


def process_datasets(
    datasets: Dict,
    apps_test_ids: Set[str],
    cc_test_ids: Set[str],
    solvita_data_ids: Set[str],
    max_problems: Optional[int] = None,
    max_correct_solutions: Optional[int] = None,
    max_incorrect_solutions: Optional[int] = None,
    dataset_filter: Optional[List[str]] = None,
    dataset_limit: Optional[Dict[str, int]] = None,
    filter_cc_lang: bool = True,
    debug: bool = False,
    progress_interval: int = 500,
) -> List[Dict[str, Any]]:
    """
    处理所有数据集，生成 solvita-train
    
    Args:
        datasets: 数据集字典
        apps_test_ids: APPS 测试集 ID 集合
        cc_test_ids: CodeContests 测试集 ID 集合
        solvita_data_ids: solvita-data 已存在 ID 集合
        max_problems: 最大生成题目数量（None 表示不限制）
        max_correct_solutions: 最大正确解数量限制（None 表示不限制）
        max_incorrect_solutions: 最大错误解数量限制（None 表示不限制）
        dataset_filter: 仅处理指定数据集列表（code-contests-plus/code-contests/apps 可多选）
        dataset_limit: 与 dataset_filter 配合，每个数据集的实例数量上限 {dataset_name: limit}
        debug: 是否输出调试信息
        progress_interval: 每处理多少题打印一次进度（0 表示不打印）
    """
    train_problems: List[Dict[str, Any]] = []
    seen_ids: Set[str] = set()
    
    # 统计信息（ccp.low_tpr: 因 true_positive_rate < 0.9 跳过的数量）
    stats = {
        "ccp": {"processed": 0, "added": 0, "skipped": 0, "no_id": 0, "duplicate": 0, "filtered": 0, "low_tpr": 0},
        "cc": {"processed": 0, "added": 0, "skipped": 0, "no_id": 0, "duplicate": 0, "filtered": 0},
        "apps": {"processed": 0, "added": 0, "skipped": 0, "no_id": 0, "duplicate": 0, "filtered": 0},
    }
    
    # 1. code-contests (train) —— 优先处理，以便 tags 从 cf_tags 直接获取
    if dataset_filter and "code-contests" not in dataset_filter:
        pass  # 跳过
    elif "code_contests" in datasets and (not max_problems or len(train_problems) < max_problems):
        limit_cc = dataset_limit.get("code-contests") if dataset_limit else None
        if limit_cc and stats["cc"]["added"] >= limit_cc:
            pass  # 已达成该数据集 limit，跳过
        else:
            print("\n" + "=" * 60)
            print("Processing code-contests (train)...")
            print("=" * 60)
            cc_train = datasets["code_contests"]["train"]
            total_cc = len(cc_train)
            print(f"  Total problems in dataset: {total_cc}")
            if limit_cc:
                print(f"  Limit for this dataset: {limit_cc}")
            if max_problems:
                print(f"  Global max_problems: {max_problems} (current: {len(train_problems)})")
            t_start_cc = time.time()

            for idx, problem in enumerate(cc_train):
                if max_problems and len(train_problems) >= max_problems:
                    print(f"  Reached global max_problems ({max_problems}), stopping...")
                    break
                if limit_cc and stats["cc"]["added"] >= limit_cc:
                    print(f"  Reached dataset limit ({limit_cc}), stopping...")
                    break
                
                stats["cc"]["processed"] += 1
                n = idx + 1
                if progress_interval > 0 and n % progress_interval == 0:
                    elapsed = time.time() - t_start_cc
                    pct = 100.0 * n / total_cc
                    print(f"  [CC] {n}/{total_cc} ({pct:.1f}%) | added: {stats['cc']['added']} | elapsed: {elapsed:.0f}s")
                elif debug and n % 1000 == 0:
                    print(f"  Progress: {n}/{total_cc} processed, {stats['cc']['added']} added")
                
                problem_id = generate_id_from_cc(problem)
                if not problem_id:
                    stats["cc"]["no_id"] += 1
                    stats["cc"]["skipped"] += 1
                    continue
                
                if problem_id in seen_ids:
                    stats["cc"]["duplicate"] += 1
                    stats["cc"]["skipped"] += 1
                    continue
                
                source_int = problem.get("source")
                source = CC_SOURCE_MAP.get(source_int, "unknown")
                if should_include_problem(problem_id, source, apps_test_ids, cc_test_ids, solvita_data_ids):
                    fields = extract_fields_from_cc(
                        problem,
                        max_correct_solutions=max_correct_solutions,
                        max_incorrect_solutions=max_incorrect_solutions,
                        filter_cc_lang=filter_cc_lang
                    )
                    tags = get_tags_for_cc(problem)
                    # 过滤后若无合法语言的 correct_solution，跳过整道题
                    if not fields.get("correct_solution"):
                        stats["cc"]["filtered"] += 1
                        stats["cc"]["skipped"] += 1
                        continue
                    seen_ids.add(problem_id)
                    train_problems.append({
                        "id": problem_id,
                        "dataset": "code-contests",
                        "description": fields["description"],
                        "test_case": fields.get("test_case"),
                        "correct_solution": fields["correct_solution"],
                        "incorrect_solution": fields["incorrect_solution"],
                        "tags": tags,
                    })
                    stats["cc"]["added"] += 1
                    if debug and stats["cc"]["added"] <= 5:
                        print(f"    [DEBUG] Added: {problem_id} (source: {source})")
                else:
                    stats["cc"]["filtered"] += 1
                    stats["cc"]["skipped"] += 1
            
            print(f"  Added: {stats['cc']['added']}, Skipped: {stats['cc']['skipped']}")
            if debug:
                print(f"    - No ID: {stats['cc']['no_id']}, Duplicate: {stats['cc']['duplicate']}, Filtered: {stats['cc']['filtered']}")
    
    # 2. code-contests-plus 1x
    if dataset_filter and "code-contests-plus" not in dataset_filter:
        pass  # 跳过
    elif "code_contests_plus" in datasets:
        print("\n" + "=" * 60)
        print("Processing code-contests-plus 1x...")
        print("=" * 60)
        ccp = datasets["code_contests_plus"]
        # ccplus_1x 从本地 parquet 加载为 list；兼容 Dataset/DatasetDict
        if isinstance(ccp, list):
            ccp_data = ccp
        elif isinstance(ccp, DatasetDict):
            ccp_data = ccp.get("train", ccp.get("default", list(ccp.values())[0]))
        else:
            ccp_data = ccp
        
        total_ccp = len(ccp_data)
        limit_ccp = dataset_limit.get("code-contests-plus") if dataset_limit else None
        print(f"  Total problems in dataset: {total_ccp}")
        if limit_ccp:
            print(f"  Limit for this dataset: {limit_ccp}")
        if max_problems:
            print(f"  Global max_problems: {max_problems} (current: {len(train_problems)})")
        t_start_ccp = time.time()

        for idx, problem in enumerate(ccp_data):
            if max_problems and len(train_problems) >= max_problems:
                print(f"  Reached global max_problems ({max_problems}), stopping...")
                break
            if limit_ccp and stats["ccp"]["added"] >= limit_ccp:
                print(f"  Reached dataset limit ({limit_ccp}), stopping...")
                break
            
            stats["ccp"]["processed"] += 1
            n = idx + 1
            if progress_interval > 0 and n % progress_interval == 0:
                elapsed = time.time() - t_start_ccp
                pct = 100.0 * n / total_ccp
                print(f"  [CC+] {n}/{total_ccp} ({pct:.1f}%) | added: {stats['ccp']['added']} | elapsed: {elapsed:.0f}s")
            elif debug and n % 1000 == 0:
                print(f"  Progress: {n}/{total_ccp} processed, {stats['ccp']['added']} added")
            
            # ccplus_1x: 仅录入 true_positive_rate >= 0.9 的题目，None 或 < 0.9 则跳过
            tpr = problem.get("true_positive_rate")
            if tpr is None or tpr < 0.9:
                stats["ccp"]["low_tpr"] += 1
                stats["ccp"]["filtered"] += 1
                stats["ccp"]["skipped"] += 1
                continue
            
            problem_id = generate_id_from_ccplus(problem)
            if not problem_id:
                stats["ccp"]["no_id"] += 1
                stats["ccp"]["skipped"] += 1
                continue
            
            if problem_id in seen_ids:
                stats["ccp"]["duplicate"] += 1
                stats["ccp"]["skipped"] += 1
                continue
            
            source = problem.get("source", "").lower()
            if should_include_problem(problem_id, source, apps_test_ids, cc_test_ids, solvita_data_ids):
                fields = extract_fields_from_ccplus(
                    problem,
                    max_correct_solutions=max_correct_solutions,
                    max_incorrect_solutions=max_incorrect_solutions
                )
                tags = get_tags_for_ccplus(problem, problem_id)
                # 过滤后若无合法语言的 correct_solution，跳过整道题
                if not fields.get("correct_solution"):
                    stats["ccp"]["filtered"] += 1
                    stats["ccp"]["skipped"] += 1
                    continue
                seen_ids.add(problem_id)
                train_problems.append({
                    "id": problem_id,
                    "dataset": "code-contests-plus",
                    "description": fields["description"],
                    "test_case": fields.get("test_case"),
                    "correct_solution": fields["correct_solution"],
                    "incorrect_solution": fields["incorrect_solution"],
                    "tags": tags,
                })
                stats["ccp"]["added"] += 1
                if debug and stats["ccp"]["added"] <= 5:
                    print(f"    [DEBUG] Added: {problem_id} (source: {source})")
            else:
                stats["ccp"]["filtered"] += 1
                stats["ccp"]["skipped"] += 1
        
        print(f"  Added: {stats['ccp']['added']}, Skipped: {stats['ccp']['skipped']}")
        if debug:
            low_tpr = stats['ccp'].get('low_tpr', 0)
            print(f"    - No ID: {stats['ccp']['no_id']}, Duplicate: {stats['ccp']['duplicate']}, Filtered: {stats['ccp']['filtered']}, Low TPR: {low_tpr}")
    
    # 3. APPS (train)
    if dataset_filter and "apps" not in dataset_filter:
        pass  # 跳过
    elif "apps" in datasets and (not max_problems or len(train_problems) < max_problems):
        limit_apps = dataset_limit.get("apps") if dataset_limit else None
        if limit_apps and stats["apps"]["added"] >= limit_apps:
            pass  # 已达成该数据集 limit，跳过
        else:
            print("\n" + "=" * 60)
            print("Processing APPS (train)...")
            print("=" * 60)
            apps_train = datasets["apps"]["train"]
            # 将 CodeChef 题目优先处理，确保小型数据集中包含若干 CodeChef 题
            codechef_problems = []
            other_problems = []
            for problem in apps_train:
                url = problem.get("url", "")
                parsed = parse_apps_url(url)
                if parsed and parsed[0].lower() == "codechef":
                    codechef_problems.append(problem)
                else:
                    other_problems.append(problem)
            apps_iterable = codechef_problems + other_problems
            total_apps = len(apps_iterable)
            print(f"  Total problems in dataset: {total_apps} (CodeChef: {len(codechef_problems)}, others: {len(other_problems)})")
            if limit_apps:
                print(f"  Limit for this dataset: {limit_apps}")
            if max_problems:
                print(f"  Global max_problems: {max_problems} (current: {len(train_problems)})")
            t_start_apps = time.time()

            for idx, problem in enumerate(apps_iterable):
                if max_problems and len(train_problems) >= max_problems:
                    print(f"  Reached global max_problems ({max_problems}), stopping...")
                    break
                if limit_apps and stats["apps"]["added"] >= limit_apps:
                    print(f"  Reached dataset limit ({limit_apps}), stopping...")
                    break
                
                stats["apps"]["processed"] += 1
                n = idx + 1
                if progress_interval > 0 and n % progress_interval == 0:
                    elapsed = time.time() - t_start_apps
                    pct = 100.0 * n / total_apps
                    print(f"  [APPS] {n}/{total_apps} ({pct:.1f}%) | added: {stats['apps']['added']} | elapsed: {elapsed:.0f}s")
                elif debug and n % 1000 == 0:
                    print(f"  Progress: {n}/{total_apps} processed, {stats['apps']['added']} added")
                
                problem_id = generate_id_from_apps(problem)
                if not problem_id:
                    stats["apps"]["no_id"] += 1
                    stats["apps"]["skipped"] += 1
                    continue
                
                if problem_id in seen_ids:
                    stats["apps"]["duplicate"] += 1
                    stats["apps"]["skipped"] += 1
                    continue
                
                url = problem.get("url", "")
                parsed = parse_apps_url(url)
                if not parsed:
                    stats["apps"]["skipped"] += 1
                    continue
                
                source, _ = parsed
                if should_include_problem(problem_id, source, apps_test_ids, cc_test_ids, solvita_data_ids):
                    fields = extract_fields_from_apps(
                        problem,
                        max_correct_solutions=max_correct_solutions,
                        max_incorrect_solutions=max_incorrect_solutions,
                        filter_lang=filter_cc_lang,  # 复用同一个过滤开关
                    )
                    # 过滤后若无合法语言的 correct_solution，跳过整道题
                    if not fields.get("correct_solution"):
                        stats["apps"]["filtered"] += 1
                        stats["apps"]["skipped"] += 1
                        continue
                    tags = get_tags_for_apps(url, parsed, problem_id)
                    train_problems.append({
                        "id": problem_id,
                        "dataset": "apps",
                        "description": fields["description"],
                        "test_case": fields.get("test_case"),
                        "correct_solution": fields["correct_solution"],
                        "incorrect_solution": fields["incorrect_solution"],
                        "tags": tags,
                    })
                    seen_ids.add(problem_id)
                    stats["apps"]["added"] += 1
                    if debug and stats["apps"]["added"] <= 5:
                        print(f"    [DEBUG] Added: {problem_id} (source: {source})")
                else:
                    stats["apps"]["filtered"] += 1
                    stats["apps"]["skipped"] += 1
            
            print(f"  Added: {stats['apps']['added']}, Skipped: {stats['apps']['skipped']}")
            if debug:
                print(f"    - No ID: {stats['apps']['no_id']}, Duplicate: {stats['apps']['duplicate']}, Filtered: {stats['apps']['filtered']}")
    
    # 输出汇总统计
    print("\n" + "=" * 60)
    print("Summary Statistics")
    print("=" * 60)
    print(f"Total train set size: {len(train_problems)} problems")
    print(f"\nBy dataset:")
    low_tpr = stats['ccp'].get('low_tpr', 0)
    print(f"  code-contests: {stats['cc']['added']} added, {stats['cc']['processed']} processed")
    print(f"  code-contests-plus: {stats['ccp']['added']} added, {stats['ccp']['processed']} processed, {low_tpr} skipped (TPR<0.9)")
    print(f"  APPS: {stats['apps']['added']} added, {stats['apps']['processed']} processed")
    
    if dataset_limit:
        print(f"\nPer-dataset limits applied: {dataset_limit}")
    if max_problems:
        print(f"Global max_problems: {max_problems}")
    if max_correct_solutions or max_incorrect_solutions:
        print(f"\nSolution limits applied:")
        if max_correct_solutions:
            print(f"  Max correct solutions per problem: {max_correct_solutions}")
        if max_incorrect_solutions:
            print(f"  Max incorrect solutions per problem: {max_incorrect_solutions}")
    
    print("=" * 60)
    
    return train_problems


def save_solvita_train(train_problems: List[Dict[str, Any]], debug: bool = False):
    """保存 solvita-train 数据集"""
    # 保存为 JSON Lines 格式
    output_file = OUTPUT_DIR / "solvita_train_tanh.jsonl"
    
    print(f"\nSaving to {output_file}...")
    
    # 统计信息
    dataset_counts = defaultdict(int)
    has_test_case = 0
    has_correct_solution = 0
    has_incorrect_solution = 0
    
    with open(output_file, "w", encoding="utf-8") as f:
        for problem in train_problems:
            dataset_counts[problem.get("dataset", "unknown")] += 1
            if problem.get("test_case"):
                has_test_case += 1
            if problem.get("correct_solution"):
                has_correct_solution += 1
            if problem.get("incorrect_solution"):
                has_incorrect_solution += 1
            
            f.write(json.dumps(problem, ensure_ascii=False) + "\n")
    
    print(f"Saved {len(train_problems)} problems to {output_file}")
    
    # 打印前5个实例
    print(f"\n{'='*60}")
    print("First 5 instances from saved JSONL file:")
    print(f"{'='*60}")
    try:
        with open(output_file, "r", encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                if i > 0:
                    break
                try:
                    instance = json.loads(line.strip())
                    print(f"\n[Instance {i}]")
                    print(f"  ID: {instance.get('id', 'N/A')}")
                    print(f"  Dataset: {instance.get('dataset', 'N/A')}")
                    print(f"  Description length: {len(instance.get('description', ''))} chars")
                    print(f"  Has test_case: {bool(instance.get('test_case'))}")
                    print(f"  Has correct_solution: {bool(instance.get('correct_solution'))}")
                    print(f"  Has incorrect_solution: {bool(instance.get('incorrect_solution'))}")
                    # 打印完整 JSON（格式化）
                    print(f"  Full JSON:")
                    print(json.dumps(instance, ensure_ascii=False, indent=4))
                except json.JSONDecodeError as e:
                    print(f"  Error parsing line {i}: {e}")
    except Exception as e:
        print(f"Error reading file: {e}")
    print(f"{'='*60}\n")
    
    if debug:
        print(f"\nDataset distribution:")
        for dataset, count in sorted(dataset_counts.items(), key=lambda x: -x[1]):
            percentage = count / len(train_problems) * 100
            print(f"  {dataset}: {count} ({percentage:.1f}%)")
        
        print(f"\nField statistics:")
        print(f"  Has test_case: {has_test_case} ({has_test_case/len(train_problems)*100:.1f}%)")
        print(f"  Has correct_solution: {has_correct_solution} ({has_correct_solution/len(train_problems)*100:.1f}%)")
        print(f"  Has incorrect_solution: {has_incorrect_solution} ({has_incorrect_solution/len(train_problems)*100:.1f}%)")
        
        # 显示前几个示例 ID
        print(f"\nFirst 10 problem IDs:")
        for i, problem in enumerate(train_problems[:10], 1):
            print(f"  {i}. {problem.get('id')} (from {problem.get('dataset')})")
    
    # 同时保存为 Hugging Face Dataset 格式
    try:
        from datasets import Dataset as HFDataset
        print(f"\nSaving as Hugging Face Dataset...")
        dataset = HFDataset.from_list(train_problems)
        hf_output_dir = OUTPUT_DIR / "solvita_train_hf"
        dataset.save_to_disk(str(hf_output_dir))
        print(f"Also saved as Hugging Face Dataset to {hf_output_dir}")
    except Exception as e:
        print(f"Warning: Failed to save as Hugging Face Dataset: {e}")


def load_datasets(debug: bool = False, dataset_filter: Optional[List[str]] = None):
    """加载数据集。若指定 dataset_filter，仅加载其中的数据集及构建测试集所需的依赖。"""
    print("Loading datasets...")
    
    datasets = {}
    
    # 构建测试集 ID 需要 apps 和 code_contests，因此始终加载；code-contests-plus 可按需加载
    need_apps = True  # 用于 test IDs 或数据源
    need_cc = True    # 用于 test IDs 或数据源
    need_ccp = dataset_filter is None or "code-contests-plus" in dataset_filter
    
    # 1. APPS（构建测试集需要，或作为数据源）
    if need_apps:
        print("\n[Loading] APPS...")
        apps = load_dataset("codeparrot/apps", split=None, trust_remote_code=True)
        datasets["apps"] = apps
        if debug:
            print(f"  Train: {len(apps['train'])} problems")
            print(f"  Test: {len(apps['test'])} problems")
            if len(apps['train']) > 0:
                example = apps['train'][0]
                print(f"  Example keys: {list(example.keys())[:10]}...")
    
    # 2. CodeContests（构建测试集需要，或作为数据源）
    if need_cc:
        print("\n[Loading] CodeContests...")
        cc = load_dataset("deepmind/code_contests")
        datasets["code_contests"] = cc
        if debug:
            print(f"  Train: {len(cc['train'])} problems")
            print(f"  Test: {len(cc['test'])} problems")
            if len(cc['train']) > 0:
                example = cc['train'][0]
                print(f"  Example keys: {list(example.keys())[:10]}...")
    
    # 3. Code-Contests-Plus 1x
    if need_ccp:
        print("\n[Loading] Code-Contests-Plus 1x...")
        ccp = load_dataset("ByteDance-Seed/Code-Contests-Plus", "1x")
        datasets["code_contests_plus"] = ccp
        if debug:
            if isinstance(ccp, DatasetDict):
                for split_name, split in ccp.items():
                    print(f"  {split_name}: {len(split)} problems")
            else:
                print(f"  Total: {len(ccp)} problems")
            if len(ccp) > 0:
                if isinstance(ccp, DatasetDict):
                    example = list(ccp.values())[0][0]
                else:
                    example = ccp[0]
                print(f"  Example keys: {list(example.keys())[:10]}...")
    
    return datasets


def main():
    parser = argparse.ArgumentParser(
        description="构建 solvita-train 数据集",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 生成完整大数据集（CC + CC+ + APPS 全部训练集，无 limit）
  python build_solvita_train.py --progress-interval 500
  
  # 生成小型测试集（100条）
  python build_solvita_train.py --max-problems 100
  
  # 限制每个题目的 solution 数量（减少数据集大小）
  python build_solvita_train.py --max-correct-solutions 5 --max-incorrect-solutions 3
  
  # 组合使用：小型测试集 + 限制 solution 数量 + 调试输出
  python build_solvita_train.py --max-problems 100 --max-correct-solutions 5 --max-incorrect-solutions 3 --debug
  
  # 仅从指定数据集获取数据（如 code-contests-plus）
  python build_solvita_train.py --dataset code-contests-plus
  
  # 从指定数据集获取固定数量的实例（如 100 条）
  python build_solvita_train.py --dataset apps --limit 100
  
  # 多个数据集时，limit 按 --dataset 顺序分别指定每个数据集各取几条
  python build_solvita_train.py --dataset code-contests-plus apps --limit 100 50
  
  # 需要总实例数上限时使用 --max-problems
  python build_solvita_train.py --dataset code-contests-plus apps --limit 200 200 --max-problems 300
  
  # CC 数据集不过滤语言，保留所有 solution（含 Java、Python2 等）
  python build_solvita_train.py --no-filter-cc-lang
        """
    )
    parser.add_argument(
        "--max-problems",
        type=int,
        default=None,
        help="最大生成题目数量（用于测试，None 表示不限制）"
    )
    parser.add_argument(
        "--max-correct-solutions",
        type=int,
        default=None,
        help="每个题目最大正确解数量限制（None 表示不限制，用于减少数据集大小）"
    )
    parser.add_argument(
        "--max-incorrect-solutions",
        type=int,
        default=None,
        help="每个题目最大错误解数量限制（None 表示不限制，用于减少数据集大小）"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="启用调试输出（显示详细的处理信息）"
    )
    parser.add_argument(
        "--dataset",
        type=str,
        choices=DATASET_NAMES,
        nargs="+",
        default=None,
        help="指定源数据集（可多个），仅从这些数据集获取实例（不指定则按默认顺序使用全部数据集）"
    )
    parser.add_argument(
        "--limit",
        type=int,
        nargs="+",
        default=None,
        help="与 --dataset 配合使用：按 --dataset 顺序分别指定每个数据集各取几条（数量需与 --dataset 个数一致）"
    )
    parser.add_argument(
        "--no-filter-cc-lang",
        action="store_true",
        help="CC 数据集不过滤语言：保留所有 solution（默认仅保留 CPP 和 Python3）"
    )
    parser.add_argument(
        "--progress-interval",
        type=int,
        default=500,
        help="每处理多少题打印一次进度（0=不打印，默认 500）"
    )
    
    args = parser.parse_args()
    
    if args.limit is not None:
        if not args.dataset or len(args.dataset) == 0:
            parser.error("--limit 必须与 --dataset 配合使用")
        if len(args.limit) != len(args.dataset):
            parser.error(f"--limit 需提供 {len(args.dataset)} 个数字（与 --dataset 一一对应），当前为 {len(args.limit)} 个")
    
    print("=" * 60)
    print("Building solvita-train dataset")
    print("=" * 60)
    if args.max_problems:
        print(f"Max problems limit: {args.max_problems}")
    if args.max_correct_solutions:
        print(f"Max correct solutions per problem: {args.max_correct_solutions}")
    if args.max_incorrect_solutions:
        print(f"Max incorrect solutions per problem: {args.max_incorrect_solutions}")
    if args.debug:
        print("Debug mode: ON")
    if args.dataset:
        print(f"Dataset filter: {', '.join(args.dataset)} only")
        if args.limit is not None:
            limits_str = ", ".join(f"{d}={n}" for d, n in zip(args.dataset, args.limit))
            print(f"Limit per dataset: {limits_str}")
    if args.no_filter_cc_lang:
        print("CC language filter: OFF (keep all solutions)")
    if args.progress_interval > 0:
        print(f"Progress interval: every {args.progress_interval} problems")
    print("=" * 60)
    
    # 1. 加载已存在的 solvita-data
    print("\n[Step 1] Loading existing solvita-data...")
    solvita_data_ids = load_existing_solvita_data_ids()
    
    # 2. 加载数据集
    print("\n[Step 2] Loading datasets...")
    datasets = load_datasets(debug=args.debug, dataset_filter=args.dataset)
    
    # 3. 构建测试集 ID 集合
    print("\n[Step 3] Building test set IDs...")
    apps_test_ids, cc_test_ids = build_test_set_ids(datasets, debug=args.debug)
    
    # 4. 处理数据集，生成训练集
    print("\n[Step 4] Processing datasets...")
    # 构建每个数据集的 limit 映射
    dataset_limit_map = None
    if args.dataset and args.limit is not None:
        dataset_limit_map = dict(zip(args.dataset, args.limit))
    
    train_problems = process_datasets(
        datasets,
        apps_test_ids,
        cc_test_ids,
        solvita_data_ids,
        max_problems=args.max_problems,
        max_correct_solutions=args.max_correct_solutions,
        max_incorrect_solutions=args.max_incorrect_solutions,
        dataset_filter=args.dataset,
        dataset_limit=dataset_limit_map,
        filter_cc_lang=not args.no_filter_cc_lang,
        debug=args.debug,
        progress_interval=args.progress_interval,
    )
    
    # 5. 保存结果
    print("\n[Step 5] Saving results...")
    save_solvita_train(train_problems, debug=args.debug)
    
    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)


if __name__ == "__main__":
    main()
