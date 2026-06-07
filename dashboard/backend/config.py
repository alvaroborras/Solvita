from __future__ import annotations

import os
import socket
import sys
from dataclasses import dataclass
from pathlib import Path


def _resolve_path(value: str | None, default: Path) -> Path:
    if value:
        return Path(value).expanduser().resolve()
    return default.expanduser().resolve()


def _parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def resolve_python_bin(
    project_root: Path,
    *,
    env: dict[str, str] | None = None,
    current_python: str | None = None,
) -> Path:
    resolved_env = os.environ if env is None else env
    override = resolved_env.get("ALGOPILOT_PYTHON") or resolved_env.get("ALGOPILOT_DASHBOARD_PYTHON")
    if override:
        return Path(override).expanduser()

    candidates = [
        project_root / ".venv" / "bin" / "python",
        project_root / ".venv" / "Scripts" / "python.exe",
        project_root / ".venv" / "Scripts" / "python",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate

    return Path(current_python or sys.executable).expanduser()


def find_available_port(host: str = "127.0.0.1", preferred_port: int = 0) -> int:
    def _reserve(port: int) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
            return int(sock.getsockname()[1])

    if preferred_port > 0:
        try:
            return _reserve(preferred_port)
        except OSError:
            pass
    return _reserve(0)


@dataclass(frozen=True)
class DashboardSettings:
    project_root: Path
    dashboard_root: Path
    data_dir: Path
    codeforces_cache_path: Path
    problems_dir: Path
    dag_definition_path: Path
    frontend_dist_dir: Path
    main_py: Path
    venv_python: Path
    host: str
    port: int
    cors_origins: list[str]
    cors_origin_regex: str


def load_settings(
    *,
    env: dict[str, str] | None = None,
    base_file: str | Path | None = None,
    current_python: str | None = None,
) -> DashboardSettings:
    resolved_env = dict(os.environ if env is None else env)
    resolved_base_file = Path(base_file or __file__).expanduser().resolve()
    dashboard_root = resolved_base_file.parents[1]
    default_project_root = resolved_base_file.parents[2]
    project_root = _resolve_path(resolved_env.get("ALGOPILOT_PROJECT_ROOT"), default_project_root)

    data_dir = _resolve_path(
        resolved_env.get("ALGOPILOT_DASHBOARD_DATA_DIR"),
        dashboard_root / "data" / "runs",
    )
    codeforces_cache_path = _resolve_path(
        resolved_env.get("ALGOPILOT_CODEFORCES_CACHE_PATH"),
        dashboard_root / "data" / "codeforces" / "cache.json",
    )
    problems_dir = _resolve_path(
        resolved_env.get("ALGOPILOT_PROBLEMS_DIR"),
        project_root / "data" / "problem",
    )
    dag_definition_path = _resolve_path(
        resolved_env.get("ALGOPILOT_DASHBOARD_DAG_DEFINITION"),
        dashboard_root / "dag-definition.json",
    )
    frontend_dist_dir = _resolve_path(
        resolved_env.get("ALGOPILOT_DASHBOARD_FRONTEND_DIST"),
        dashboard_root / "frontend" / "dist",
    )
    main_py = _resolve_path(
        resolved_env.get("ALGOPILOT_DASHBOARD_MAIN_PY"),
        project_root / "main.py",
    )
    host = resolved_env.get("ALGOPILOT_DASHBOARD_HOST", "127.0.0.1")
    port = int(resolved_env.get("ALGOPILOT_DASHBOARD_PORT", "8766"))
    cors_origins = _parse_csv(resolved_env.get("ALGOPILOT_DASHBOARD_CORS_ORIGINS"))
    cors_origin_regex = resolved_env.get(
        "ALGOPILOT_DASHBOARD_CORS_ORIGIN_REGEX",
        r"https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    )

    return DashboardSettings(
        project_root=project_root,
        dashboard_root=dashboard_root,
        data_dir=data_dir,
        codeforces_cache_path=codeforces_cache_path,
        problems_dir=problems_dir,
        dag_definition_path=dag_definition_path,
        frontend_dist_dir=frontend_dist_dir,
        main_py=main_py,
        venv_python=resolve_python_bin(
            project_root,
            env=resolved_env,
            current_python=current_python,
        ),
        host=host,
        port=port,
        cors_origins=cors_origins,
        cors_origin_regex=cors_origin_regex,
    )


SETTINGS = load_settings()

PROJECT_ROOT = SETTINGS.project_root
DASHBOARD_ROOT = SETTINGS.dashboard_root
DATA_DIR = SETTINGS.data_dir
CODEFORCES_CACHE_PATH = SETTINGS.codeforces_cache_path
PROBLEMS_DIR = SETTINGS.problems_dir
DAG_DEFINITION_PATH = SETTINGS.dag_definition_path
FRONTEND_DIST_DIR = SETTINGS.frontend_dist_dir
VENV_PYTHON = SETTINGS.venv_python
MAIN_PY = SETTINGS.main_py
HOST = SETTINGS.host
PORT = SETTINGS.port
CORS_ORIGINS = SETTINGS.cors_origins
CORS_ORIGIN_REGEX = SETTINGS.cors_origin_regex
