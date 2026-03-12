import pytest
from unittest.mock import MagicMock
from src.nodes.generator_semantic import generate_semantic_test_program
from src.nodes.generator_stress import generate_stress_test_program
from src.nodes.generator_anti_hash import generate_anti_hash_test_program

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

def test_semantic_generator_fallback(mock_state, mock_report):
    llm = MagicMock()
    # Mock LLM generates dangerous syscalls
    llm.generate.return_value = '#include <unistd.h>\nint main(){ system("rm -rf"); return 0; }'
    
    code = generate_semantic_test_program(mock_state, llm, mock_report)
    assert "return 1;" in code  # fallback code
    assert "system" not in code

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
