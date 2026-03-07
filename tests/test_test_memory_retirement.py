import pytest


def test_nodes_module_no_longer_exports_update_test_memory_node():
    import src.nodes as nodes

    with pytest.raises(AttributeError):
        getattr(nodes, "update_test_memory_node")


def test_codegen_workflow_no_longer_contains_update_test_memory():
    from src.graph.workflow import create_codegen_subgraph

    graph = create_codegen_subgraph().get_graph()
    mermaid = graph.draw_mermaid()

    assert "update_test_memory" not in mermaid
