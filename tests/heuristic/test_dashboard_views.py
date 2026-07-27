from dashboard.backend import heuristic_views
from src.heuristic.storage import HeuristicStore


def test_read_only_dashboard_views(monkeypatch, tmp_path):
    monkeypatch.setenv("SOLVITA_HEURISTIC_DATA_DIR", str(tmp_path))
    store = HeuristicStore(tmp_path / "heuristic.sqlite3")
    store.create_run("run", "ogc", "solvita_dgs", {"proposals": 1})
    store.checkpoint(
        "run",
        {
            "run_id": "run",
            "proposals": 1,
            "support_calls": 0,
            "archive": {"entries": []},
        },
    )
    store.close()

    runs = heuristic_views.heuristic_runs()
    assert runs["runs"][0]["run_id"] == "run"
    detail = heuristic_views.heuristic_run("run")
    assert detail["report"]["proposals"] == 1
    trajectory = heuristic_views.heuristic_trajectory("run")
    assert trajectory["events"] == []
