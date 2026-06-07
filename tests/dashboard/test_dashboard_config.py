from __future__ import annotations

import socket
from pathlib import Path

from dashboard.backend.config import find_available_port, load_settings
from dashboard.backend.models import (
    CodeforcesImportRequest,
    CodeforcesSearchResponse,
    CodeforcesSearchResult,
)
from scripts import start_dashboard

ROOT = Path(__file__).resolve().parents[2]
LEGACY_DASHBOARD_PREFIX = "SOL" "VITA_DASHBOARD_"


def test_load_settings_prefers_cross_platform_virtualenv_python(tmp_path: Path):
    project_root = tmp_path / "repo"
    backend_dir = project_root / "dashboard" / "backend"
    backend_dir.mkdir(parents=True)

    windows_python = project_root / ".venv" / "Scripts" / "python.exe"
    windows_python.parent.mkdir(parents=True)
    windows_python.write_text("", encoding="utf-8")

    settings = load_settings(
        env={},
        base_file=backend_dir / "config.py",
        current_python="/usr/bin/python3",
    )

    assert settings.project_root == project_root
    assert settings.venv_python == windows_python


def test_load_settings_reads_env_overrides_and_frontend_dist(tmp_path: Path):
    project_root = tmp_path / "repo"
    backend_dir = project_root / "dashboard" / "backend"
    backend_dir.mkdir(parents=True)
    custom_problem_dir = tmp_path / "problems"
    custom_problem_dir.mkdir()
    custom_runs_dir = tmp_path / "runs"
    custom_runs_dir.mkdir()
    custom_dist_dir = tmp_path / "frontend-dist"
    custom_dist_dir.mkdir()

    settings = load_settings(
        env={
            "ALGOPILOT_DASHBOARD_HOST": "0.0.0.0",
            "ALGOPILOT_DASHBOARD_PORT": "9900",
            "ALGOPILOT_DASHBOARD_CORS_ORIGINS": "http://localhost:3000,http://127.0.0.1:4173",
            "ALGOPILOT_DASHBOARD_CORS_ORIGIN_REGEX": r"https?://example\.com(:\d+)?$",
            "ALGOPILOT_PROBLEMS_DIR": str(custom_problem_dir),
            "ALGOPILOT_DASHBOARD_DATA_DIR": str(custom_runs_dir),
            "ALGOPILOT_DASHBOARD_FRONTEND_DIST": str(custom_dist_dir),
            "ALGOPILOT_PYTHON": "/custom/python",
        },
        base_file=backend_dir / "config.py",
        current_python="/usr/bin/python3",
    )

    assert settings.host == "0.0.0.0"
    assert settings.port == 9900
    assert settings.cors_origins == ["http://localhost:3000", "http://127.0.0.1:4173"]
    assert settings.cors_origin_regex == r"https?://example\.com(:\d+)?$"
    assert settings.problems_dir == custom_problem_dir
    assert settings.data_dir == custom_runs_dir
    assert settings.frontend_dist_dir == custom_dist_dir
    assert settings.venv_python == Path("/custom/python")


def test_load_settings_exposes_codeforces_cache_path(tmp_path: Path):
    project_root = tmp_path / "repo"
    backend_dir = project_root / "dashboard" / "backend"
    backend_dir.mkdir(parents=True)
    cache_path = tmp_path / "cf-cache.json"

    settings = load_settings(
        env={"ALGOPILOT_CODEFORCES_CACHE_PATH": str(cache_path)},
        base_file=backend_dir / "config.py",
        current_python="/usr/bin/python3",
    )

    assert settings.codeforces_cache_path == cache_path


def test_codeforces_models_accept_contest_index_and_url_forms():
    result = CodeforcesSearchResult(
        contest_id=1575,
        index="C",
        name="Cyclic Sum",
        rating=2100,
        tags=["math", "dp"],
        url="https://codeforces.com/contest/1575/problem/C",
        problem_id="codeforces_1575_C",
    )
    response = CodeforcesSearchResponse(results=[result], cache_status="ready")

    by_key = CodeforcesImportRequest(contest_id=1575, index="C")
    by_url = CodeforcesImportRequest(url="https://codeforces.com/contest/1575/problem/C")

    assert response.results[0].problem_id == "codeforces_1575_C"
    assert by_key.contest_id == 1575
    assert by_key.index == "C"
    assert by_url.url.endswith("/1575/problem/C")


def test_start_dashboard_launcher_uses_algopilot_dashboard_env_names():
    launcher = (ROOT / "scripts" / "start_dashboard.py").read_text(encoding="utf-8")

    expected_env_names = (
        "ALGOPILOT_DASHBOARD_HOST",
        "ALGOPILOT_DASHBOARD_PORT",
        "ALGOPILOT_DASHBOARD_FRONTEND_HOST",
        "ALGOPILOT_DASHBOARD_FRONTEND_PORT",
        "ALGOPILOT_DASHBOARD_BACKEND_URL",
    )

    for env_name in expected_env_names:
        assert env_name in launcher

    assert LEGACY_DASHBOARD_PREFIX not in launcher


def test_start_dashboard_backend_command_prefers_algopilot_python_override(tmp_path: Path):
    project_root = tmp_path / "repo"
    backend_dir = project_root / "dashboard" / "backend"
    backend_dir.mkdir(parents=True)
    custom_python = tmp_path / "custom-python"
    custom_python.write_text("", encoding="utf-8")

    command = start_dashboard.build_backend_cmd(
        project_root=project_root,
        env={"ALGOPILOT_DASHBOARD_PYTHON": str(custom_python)},
        current_python="/usr/bin/python3",
    )

    assert command == [str(custom_python), "server.py"]


def test_find_available_port_falls_back_when_preferred_port_is_in_use():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    occupied_port = sock.getsockname()[1]

    try:
      chosen = find_available_port("127.0.0.1", occupied_port)
    finally:
      sock.close()

    assert chosen != occupied_port
    assert chosen > 0
