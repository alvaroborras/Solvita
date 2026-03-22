import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.nodes.generate_tests import _resolve_data_root
from src.utils.problem_utils import extract_problem_code


def test_extract_problem_code_handles_loader_injected_problem_id():
    raw_problem = {
        "_metadata": {
            "problem_id": "codecontests_1575_A__Another_Sorting_Problem",
            "name": "1575_A. Another Sorting Problem",
        }
    }

    assert extract_problem_code(raw_problem) == "1575_A"


def test_resolve_data_root_defaults_to_repo_data_directory():
    resolved = _resolve_data_root({})

    assert resolved == Path("d:/solvita-2/data").resolve()


def test_resolve_data_root_honors_config_override():
    resolved = _resolve_data_root({"data_root": "d:/custom-solver-data"})

    assert resolved == Path("d:/custom-solver-data").resolve()
