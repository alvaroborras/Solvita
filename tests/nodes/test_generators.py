import pytest
from unittest.mock import MagicMock
from src.nodes.generator_semantic import (
    generate_semantic_test_program,
    repair_semantic_test_program,
)
from src.nodes.generator_stress import (
    generate_stress_test_program,
    repair_stress_test_program,
)
from src.nodes.generator_anti_hash import generate_anti_hash_test_program


def make_search_replace_block(search: str, replace: str) -> str:
    return "\n".join(
        [
            "<" * 7 + " SEARCH",
            search,
            "=" * 7,
            replace,
            ">" * 7 + " REPLACE",
        ]
    )


@pytest.fixture
def mock_state():
    return {
        "problem": {
            "description": "Find sum",
            "constraints": {"N": "1000", "A_i": "-1e9 to 1e9"}
        }
    }

@pytest.fixture
def mock_report():
    return {
        "bug_class": "overflow",
        "input_hypothesis": ["Very large negative numbers"]
    }

def test_semantic_generator_clean(mock_state, mock_report):
    llm = MagicMock()
    # Mock LLM wraps in markdown
    llm.generate.return_value = "```cpp\n#include <iostream>\nint main(){ std::cout << 1; return 0; }\n```"
    
    code = generate_semantic_test_program(mock_state, llm, mock_report)
    assert "#include <iostream>" in code
    assert "```" not in code


def test_semantic_generator_includes_memory_advice(mock_state, mock_report):
    llm = MagicMock()
    llm.generate.return_value = "int main(){ return 0; }"

    generate_semantic_test_program(
        mock_state,
        llm,
        mock_report,
        memory_advice="Prioritize duplicated-prefix strings.",
    )

    prompt = llm.generate.call_args[0][0]
    assert "HACKER STRATEGY ADVICE" in prompt
    assert "duplicated-prefix strings" in prompt


def test_semantic_generator_uses_canonical_constraints_and_retry_feedback(mock_report):
    llm = MagicMock()
    llm.generate.return_value = "int main(){ return 0; }"
    state = {
        "problem": {
            "description": "Original description",
            "constraints": {"time_limit": 2},
            "canonical": {
                "inputs": {"format": "First line n m, then n uppercase strings"},
                "constraints": {
                    "normalized": {
                        "1 <= n * m <= 10^6": "input size bound",
                        "strings are pairwise distinct": "uniqueness",
                    },
                    "derived": ["all strings must be uppercase"],
                },
                "required_properties": ["strings must be pairwise distinct"],
                "edge_cases": ["duplicate strings should be rejected"],
            },
        }
    }

    generate_semantic_test_program(
        state,
        llm,
        mock_report,
        memory_advice="Prefer duplicated-prefix edge cases.",
        previous_attempt_issues="Validation Failed: duplicate found at line 3",
        previous_generated_input="3 2\nAA\nAA\nBB\n",
    )

    prompt = llm.generate.call_args[0][0]
    assert "1 <= n * m <= 10^6" in prompt
    assert "strings are pairwise distinct" in prompt
    assert "Validation Failed: duplicate found at line 3" in prompt
    assert "3 2" in prompt
    assert "VALIDITY-FIRST" in prompt

def test_semantic_generator_fallback(mock_state, mock_report):
    llm = MagicMock()
    # Mock LLM generates dangerous syscalls
    llm.generate.return_value = '#include <unistd.h>\nint main(){ system("rm -rf"); return 0; }'
    
    code = generate_semantic_test_program(mock_state, llm, mock_report)
    assert "return 1;" in code  # fallback code
    assert "system" not in code


def test_semantic_retry_builds_checklist_then_patch_from_previous_code(mock_report):
    llm = MagicMock()
    llm.generate.side_effect = [
        """```json
        {
          "must_fix": ["enforce pairwise distinctness"],
          "do_not_regress": ["every generated string length must equal m"],
          "attack_goal": ["preserve repeated-prefix pressure"]
        }
        ```""",
        make_search_replace_block(
            'vector<string> s = {"AA", "AA", "BB"};',
            'vector<string> s = {"AA", "AB", "BB"};',
        ),
    ]
    state = {
        "problem": {
            "description": "Generate uppercase strings",
            "constraints": {"time_limit": 2},
            "canonical": {
                "inputs": {"format": "n m followed by n uppercase strings"},
                "constraints": {
                    "normalized": {"1 <= n * m <= 10^6": "size bound"},
                    "derived": ["strings are pairwise distinct"],
                },
                "required_properties": ["every string length equals m"],
                "edge_cases": ["duplicate strings should be rejected"],
            },
        }
    }
    previous_code = """#include <bits/stdc++.h>
using namespace std;
int main() {
    vector<string> s = {"AA", "AA", "BB"};
    return 0;
}
"""

    patched = repair_semantic_test_program(
        state,
        llm,
        mock_report,
        last_generator_code=previous_code,
        failure_kind="validator_rejected",
        failure_reason="Validation Failed: duplicate strings",
        previous_attempt_issues="Validation Failed: duplicate strings",
        previous_generated_input="3 2\nAA\nAA\nBB\n",
        memory_advice="Prefer repeated-prefix strings.",
    )

    assert 'vector<string> s = {"AA", "AB", "BB"};' in patched
    assert llm.generate.call_count == 2
    checklist_prompt = llm.generate.call_args_list[0].args[0]
    patch_prompt = llm.generate.call_args_list[1].args[0]
    assert "must_fix" in checklist_prompt
    assert "validator_rejected" in checklist_prompt
    assert "duplicate strings" in checklist_prompt
    assert "SEARCH/REPLACE" in patch_prompt
    assert "vector<string> s = {\"AA\", \"AA\", \"BB\"};" in patch_prompt
    assert "pairwise distinct" in patch_prompt
    assert "3 2" in patch_prompt


def test_semantic_retry_preserves_old_code_when_patch_does_not_apply(mock_report):
    llm = MagicMock()
    llm.generate.side_effect = [
        '{"must_fix":["enforce pairwise distinctness"],"do_not_regress":["keep length = m"],"attack_goal":["preserve attack shape"]}',
        make_search_replace_block(
            'vector<string> s = {"XX", "XX"};',
            'vector<string> s = {"XX", "XY"};',
        ),
    ]
    state = {
        "problem": {
            "description": "Generate uppercase strings",
            "canonical": {
                "inputs": {"format": "n m followed by n uppercase strings"},
                "constraints": {"normalized": {"1 <= n * m <= 10^6": "size bound"}},
                "required_properties": ["strings are pairwise distinct"],
            },
        }
    }
    previous_code = """#include <bits/stdc++.h>
using namespace std;
int main() {
    vector<string> s = {"AA", "AA", "BB"};
    return 0;
}
"""

    patched = repair_semantic_test_program(
        state,
        llm,
        mock_report,
        last_generator_code=previous_code,
        failure_kind="validator_rejected",
        failure_reason="Validation Failed: duplicate strings",
        previous_attempt_issues="Validation Failed: duplicate strings",
        previous_generated_input="3 2\nAA\nAA\nBB\n",
    )

    assert patched == previous_code

def test_stress_generator_clean(mock_state):
    llm = MagicMock()
    llm.generate.return_value = '```\n#include <random>\nint main(){ return 0; }\n```'
    
    code = generate_stress_test_program(mock_state, llm)
    assert "#include <random>" in code
    assert "```" not in code

def test_stress_generator_includes_random_prompt(mock_state):
    llm = MagicMock()
    llm.generate.return_value = "int main(){}"
    generate_stress_test_program(mock_state, llm)
    
    prompt = llm.generate.call_args[0][0]
    assert "<random>" in prompt
    assert "std::mt19937_64" in prompt


def test_stress_generator_uses_canonical_input_constraints():
    llm = MagicMock()
    llm.generate.return_value = "int main(){}"
    state = {
        "problem": {
            "description": "Original description",
            "constraints": {"time_limit": 2},
            "canonical": {
                "inputs": {"format": "n m then n uppercase strings"},
                "constraints": {
                    "normalized": {"1 <= n * m <= 10^6": "size bound"},
                    "derived": ["strings are pairwise distinct"],
                },
                "required_properties": ["strings are pairwise distinct"],
                "edge_cases": ["duplicate strings must be avoided"],
            },
        }
    }

    generate_stress_test_program(state, llm)
    prompt = llm.generate.call_args[0][0]
    assert "1 <= n * m <= 10^6" in prompt
    assert "pairwise distinct" in prompt


def test_stress_retry_uses_checklist_then_patch():
    llm = MagicMock()
    llm.generate.side_effect = [
        '{"must_fix":["ensure all strings have length m"],"do_not_regress":["keep output size near upper bound"],"attack_goal":["preserve large random case"]}',
        make_search_replace_block(
            'cout << "AAA\\n";',
            'cout << "AAB\\n";',
        ),
    ]
    state = {
        "problem": {
            "description": "Generate uppercase strings",
            "canonical": {
                "inputs": {"format": "n m followed by n uppercase strings"},
                "constraints": {
                    "normalized": {"1 <= n * m <= 10^6": "size bound"},
                    "derived": ["strings are pairwise distinct"],
                },
                "required_properties": ["every string length equals m"],
            },
        }
    }
    previous_code = """#include <bits/stdc++.h>
using namespace std;
int main() {
    cout << "AAA\\n";
    return 0;
}
"""

    patched = repair_stress_test_program(
        state,
        llm,
        last_generator_code=previous_code,
        failure_kind="validator_rejected",
        failure_reason="Validation Failed: string length not matching m",
        previous_attempt_issues="Validation Failed: string length not matching m",
        previous_generated_input="1 3\nAAA\n",
    )

    assert 'cout << "AAB\\n";' in patched
    assert llm.generate.call_count == 2
    checklist_prompt = llm.generate.call_args_list[0].args[0]
    patch_prompt = llm.generate.call_args_list[1].args[0]
    assert "must_fix" in checklist_prompt
    assert "string length not matching m" in checklist_prompt
    assert "SEARCH/REPLACE" in patch_prompt
    assert "1 <= n * m <= 10^6" in patch_prompt


def test_anti_hash_generator_clean(mock_state, mock_report):
    llm = MagicMock()
    llm.generate.return_value = '#include <string>\nint main(){ return 0; }'
    
    code = generate_anti_hash_test_program(mock_state, llm, mock_report)
    assert "#include <string>" in code

def test_anti_hash_generator_includes_collision_prompt(mock_state, mock_report):
    llm = MagicMock()
    llm.generate.return_value = "int main(){}"
    generate_anti_hash_test_program(mock_state, llm, mock_report)
    
    prompt = llm.generate.call_args[0][0]
    assert "collision derivation algorithm" in prompt
    assert "Thue-Morse" in prompt


def test_anti_hash_generator_uses_canonical_input_constraints(mock_report):
    llm = MagicMock()
    llm.generate.return_value = "int main(){}"
    state = {
        "problem": {
            "description": "Original description",
            "constraints": {"time_limit": 2},
            "canonical": {
                "inputs": {"format": "single string length n"},
                "constraints": {
                    "normalized": {"1 <= n <= 10^5": "length bound"},
                    "derived": ["only lowercase letters"],
                },
                "required_properties": ["output strings must stay within length bound"],
                "edge_cases": ["near-collision strings"],
            },
        }
    }

    generate_anti_hash_test_program(state, llm, mock_report)
    prompt = llm.generate.call_args[0][0]
    assert "1 <= n <= 10^5" in prompt
    assert "only lowercase letters" in prompt
