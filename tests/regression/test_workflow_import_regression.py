import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.graph.workflow import create_codegen_subgraph, create_solvita_workflow


def test_create_codegen_subgraph_builds_without_name_error():
    create_codegen_subgraph()


def test_create_solvita_workflow_builds_with_callable_hacker_settlement():
    create_solvita_workflow()
