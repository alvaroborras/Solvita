from __future__ import annotations

import re
import urllib.request
from typing import Any

from bs4 import BeautifulSoup, Tag


CODEFORCES_USER_AGENT = "AlgoPilot-Dashboard/1.0"


def _problem_url(contest_id: int, index: str) -> str:
    return f"https://codeforces.com/contest/{contest_id}/problem/{index}"


def _normalize_text(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in normalized.split("\n")]
    return "\n".join(lines).strip()


def _extract_section_text(section: Tag | None) -> str:
    if section is None:
        return ""
    section_soup = BeautifulSoup(str(section), "html.parser")
    title = section_soup.select_one(".section-title")
    if title is not None:
        title.decompose()
    return _normalize_text(section_soup.get_text("\n"))


def _extract_statement_text(problem_statement: Tag) -> str:
    parts: list[str] = []
    for child in problem_statement.children:
        if not isinstance(child, Tag):
            continue
        classes = set(child.get("class", []))
        if classes & {"header", "input-specification", "output-specification", "sample-tests"}:
            continue
        text = _normalize_text(child.get_text("\n"))
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def _extract_sample_text(pre_node: Tag) -> str:
    return _normalize_text(pre_node.get_text("\n"))


def _parse_time_limit_ms(value: str) -> int | None:
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*(milliseconds?|ms|seconds?|secs?|s)\b",
        value.lower(),
    )
    if not match:
        return None
    amount = float(match.group(1))
    unit = match.group(2)
    if unit.startswith("m"):
        return int(amount)
    return int(amount * 1000)


def _parse_memory_limit_mb(value: str) -> int | None:
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*(kilobytes?|kb|megabytes?|mb|gigabytes?|gb|bytes?)\b",
        value.lower(),
    )
    if not match:
        return None
    amount = float(match.group(1))
    unit = match.group(2)
    if unit.startswith("g"):
        return int(amount * 1024)
    if unit.startswith("m"):
        return int(amount)
    if unit.startswith("k"):
        return int(amount / 1024)
    return int(amount / (1024 * 1024))


def parse_codeforces_problem_html(
    html: str,
    contest_id: int,
    index: str,
) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    problem_statement = soup.select_one(".problem-statement")
    if problem_statement is None:
        raise ValueError("Codeforces problem statement not found")

    title_node = problem_statement.select_one(".header .title")
    if title_node is None:
        raise ValueError("Codeforces problem title not found")

    title = _normalize_text(title_node.get_text(" ", strip=True))
    name = title.split(". ", 1)[1] if ". " in title else title
    time_limit_node = problem_statement.select_one(".header .time-limit")
    memory_limit_node = problem_statement.select_one(".header .memory-limit")
    time_limit = ""
    if time_limit_node is not None:
        time_limit = _normalize_text(
            time_limit_node.get_text(" ", strip=True).replace("time limit per test", "", 1)
        )
    memory_limit = ""
    if memory_limit_node is not None:
        memory_limit = _normalize_text(
            memory_limit_node.get_text(" ", strip=True).replace("memory limit per test", "", 1)
        )

    statement_text = _extract_statement_text(problem_statement)
    input_text = _extract_section_text(problem_statement.select_one(".input-specification"))
    output_text = _extract_section_text(problem_statement.select_one(".output-specification"))

    description_parts = [part for part in [statement_text] if part]
    if input_text:
        description_parts.append(f"Input\n{input_text}")
    if output_text:
        description_parts.append(f"Output\n{output_text}")
    description = "\n\n".join(description_parts)

    sample_tests_root = problem_statement.select_one(".sample-tests")
    public_tests: list[dict[str, str]] = []
    if sample_tests_root is not None:
        inputs = sample_tests_root.select(".input pre")
        outputs = sample_tests_root.select(".output pre")
        if len(inputs) != len(outputs):
            raise ValueError(
                f"Codeforces sample count mismatch: {len(inputs)} inputs, {len(outputs)} outputs"
            )
        public_tests = [
            {
                "input": _extract_sample_text(input_node),
                "output": _extract_sample_text(output_node),
            }
            for input_node, output_node in zip(inputs, outputs)
        ]

    return {
        "contest_id": contest_id,
        "index": index,
        "title": title,
        "name": name,
        "url": _problem_url(contest_id, index),
        "time_limit": time_limit,
        "memory_limit": memory_limit,
        "statement": statement_text,
        "input_spec": input_text,
        "output_spec": output_text,
        "description": description,
        "public_tests": public_tests,
    }


def build_problem_payload(
    parsed: dict[str, Any],
    contest_id: int,
    index: str,
    rating: int | None,
    tags: list[str] | None,
) -> dict[str, Any]:
    normalized_index = str(index).strip().upper()
    problem_id = f"codeforces_{contest_id}_{normalized_index}"
    parsed_tags = list(tags or [])
    return {
        "problem_id": problem_id,
        "description": parsed["description"],
        "public_tests": parsed["public_tests"],
        "constraints": {
            "time_limit": parsed["time_limit"],
            "memory_limit": parsed["memory_limit"],
        },
        "time_limit": _parse_time_limit_ms(parsed["time_limit"]),
        "space_limit": _parse_memory_limit_mb(parsed["memory_limit"]),
        "types": parsed_tags,
        "_metadata": {
            "source": "codeforces",
            "platform": "codeforces",
            "question_id": problem_id,
            "name": parsed["title"],
            "difficulty": rating,
            "url": _problem_url(contest_id, normalized_index),
            "cf_contest_id": contest_id,
            "cf_index": normalized_index,
            "cf_rating": rating,
            "cf_tags": parsed_tags,
            "custom": False,
        },
    }


def fetch_problem_html(contest_id: int, index: str) -> str:
    request = urllib.request.Request(
        _problem_url(contest_id, index),
        headers={"User-Agent": CODEFORCES_USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")
