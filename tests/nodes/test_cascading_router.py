import pytest
from unittest.mock import MagicMock
from src.nodes.cascading_router import cascading_execution_router


def test_router_anti_hash_success(monkeypatch):
    """Test router successfully stopping at Anti-Hash if suggested and execution passes."""
    mock_anti = MagicMock(return_value=("int main(){}", []))
    monkeypatch.setattr("src.nodes.cascading_router.generate_anti_hash_test_program", mock_anti)

    mock_exec = MagicMock(return_value=(True, "collision_string", ""))
    monkeypatch.setattr("src.nodes.cascading_router.execute_generator_and_validate", mock_exec)

    llm = MagicMock()
    route, result, log, new_msgs = cascading_execution_router(
        {}, llm, {"suggested_route": "anti_hash"}
    )

    assert route == "anti_hash"
    assert "collision_string" in result
    assert mock_anti.call_count == 1
    assert mock_exec.call_count == 1
    assert isinstance(new_msgs, list)


def test_router_semantic_downgrade_to_stress(monkeypatch):
    """Test Semantic Route trying 3 times then downgrading to Stress Test."""
    mock_semantic = MagicMock(return_value=("int main(){ semantic }", []))
    mock_semantic_repair = MagicMock(return_value=("int main(){ semantic repair }", []))
    mock_stress = MagicMock(return_value=("int main(){ stress }", []))
    monkeypatch.setattr("src.nodes.cascading_router.generate_semantic_test_program", mock_semantic)
    monkeypatch.setattr("src.nodes.cascading_router.repair_semantic_test_program", mock_semantic_repair)
    monkeypatch.setattr("src.nodes.cascading_router.generate_stress_test_program", mock_stress)

    # 3 Semantic failures, 1 Stress success
    mock_exec = MagicMock(
        side_effect=[
            (False, "", "Sem Fail 1"),
            (False, "", "Sem Fail 2"),
            (False, "", "Sem Fail 3"),
            (True, "stress_output", ""),
        ]
    )
    monkeypatch.setattr("src.nodes.cascading_router.execute_generator_and_validate", mock_exec)

    llm = MagicMock()
    route, result, log, new_msgs = cascading_execution_router(
        {}, llm, {"suggested_route": "semantic"}, max_retries=3
    )

    assert mock_semantic.call_count == 1
    assert mock_semantic_repair.call_count == 2
    assert mock_stress.call_count == 1
    assert route == "stress"
    assert result == "stress_output"
    assert "All Semantic attempts failed" in "\n".join(log)
    assert isinstance(new_msgs, list)


def test_router_all_fail(monkeypatch):
    """Test what happens if the stress test fallback also fails."""
    mock_sem = MagicMock(return_value=("x", []))
    mock_sem_repair = MagicMock(return_value=("x", []))
    mock_str = MagicMock(return_value=("x", []))
    mock_str_repair = MagicMock(return_value=("x", []))
    monkeypatch.setattr("src.nodes.cascading_router.generate_semantic_test_program", mock_sem)
    monkeypatch.setattr("src.nodes.cascading_router.repair_semantic_test_program", mock_sem_repair)
    monkeypatch.setattr("src.nodes.cascading_router.generate_stress_test_program", mock_str)
    monkeypatch.setattr("src.nodes.cascading_router.repair_stress_test_program", mock_str_repair)

    # Semantic 3 fails + Stress 3 fails
    mock_exec = MagicMock(
        side_effect=[
            (False, "", "E"),
            (False, "", "E"),
            (False, "", "E"),
            (False, "", "E"),
            (False, "", "E"),
            (False, "", "E"),
        ]
    )
    monkeypatch.setattr("src.nodes.cascading_router.execute_generator_and_validate", mock_exec)

    llm = MagicMock()
    route, result, log, new_msgs = cascading_execution_router(
        {}, llm, {"suggested_route": "semantic"}, max_retries=3
    )

    assert route == "failed"
    assert "CRITICAL" in "\n".join(log)
    assert mock_sem.call_count == 1
    assert mock_sem_repair.call_count == 2
    assert mock_str.call_count == 1
    assert mock_str_repair.call_count == 2
    assert isinstance(new_msgs, list)
