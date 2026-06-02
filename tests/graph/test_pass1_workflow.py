import importlib
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


class _CompiledGraph:
    def __init__(self, nodes, edges, entry_point):
        self.nodes = nodes
        self.edges = edges
        self.entry_point = entry_point

    def get_graph(self):
        return self


class _FakeStateGraph:
    def __init__(self, *_args, **_kwargs):
        self._nodes = {}
        self._edges = []
        self._entry_point = None

    def add_node(self, name, node):
        self._nodes[name] = node

    def set_entry_point(self, name):
        self._entry_point = name

    def add_edge(self, source, target):
        self._edges.append(
            {"source": source, "target": target, "condition": None, "label": None}
        )

    def add_conditional_edges(self, source, condition, mapping):
        condition_name = getattr(condition, "__name__", str(condition))
        for label, target in mapping.items():
            self._edges.append(
                {
                    "source": source,
                    "target": target,
                    "condition": condition_name,
                    "label": label,
                }
            )

    def compile(self):
        return _CompiledGraph(dict(self._nodes), list(self._edges), self._entry_point)


def _install_fake_langgraph(monkeypatch):
    fake_graph_module = types.ModuleType("langgraph.graph")
    fake_graph_module.StateGraph = _FakeStateGraph
    fake_graph_module.END = "END"

    fake_langgraph = types.ModuleType("langgraph")
    fake_langgraph.graph = fake_graph_module

    monkeypatch.setitem(sys.modules, "langgraph", fake_langgraph)
    monkeypatch.setitem(sys.modules, "langgraph.graph", fake_graph_module)


def test_pass1_workflow_compiles_with_new_topology(monkeypatch):
    _install_fake_langgraph(monkeypatch)
    monkeypatch.delitem(sys.modules, "src.graph.workflow", raising=False)

    workflow_module = importlib.import_module("src.graph.workflow")
    workflow_module = importlib.reload(workflow_module)

    workflow = workflow_module.create_solvita_workflow()
    graph = workflow.get_graph()

    assert workflow is not None
    assert "failure_bank_lookup" in graph.nodes
    assert "pre_solve_controller" in graph.nodes
    assert "bootstrap_tests" in graph.nodes
    assert "verifier_phase" in graph.nodes
    assert "post_verify_controller" in graph.nodes
    assert {
        "source": "abstract_phase",
        "target": "failure_bank_lookup",
        "condition": None,
        "label": None,
    } in graph.edges
    assert {
        "source": "codegen_phase",
        "target": "verifier_phase",
        "condition": "post_codegen_routing",
        "label": "to_verifier",
    } in graph.edges
