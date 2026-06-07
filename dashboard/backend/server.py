from __future__ import annotations

from datetime import datetime
import json
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

try:
    from .config import (
        CODEFORCES_CACHE_PATH,
        CORS_ORIGINS,
        CORS_ORIGIN_REGEX,
        DAG_DEFINITION_PATH,
        FRONTEND_DIST_DIR,
        HOST,
        PORT,
        PROBLEMS_DIR,
        PROJECT_ROOT,
    )
    from .codeforces_catalog import CodeforcesCatalog
    from .codeforces_import import (
        build_problem_payload,
        fetch_problem_html,
        parse_codeforces_problem_html,
    )
    from .event_store import EventStore
    from .models import (
        CodeforcesImportRequest,
        CodeforcesImportResponse,
        CodeforcesSearchResponse,
        CodeforcesSearchResult,
        CustomProblemDeleteResponse,
        CustomProblemRequest,
        CustomProblemResponse,
        RunCancelResponse,
        RunDeleteResponse,
        RunRequest,
        RunResponse,
        RunSummary,
    )
    from .process_runner import ProcessManager
    from .ws_manager import WebSocketManager
except ImportError:
    from config import (
        CODEFORCES_CACHE_PATH,
        CORS_ORIGINS,
        CORS_ORIGIN_REGEX,
        DAG_DEFINITION_PATH,
        FRONTEND_DIST_DIR,
        HOST,
        PORT,
        PROBLEMS_DIR,
        PROJECT_ROOT,
    )
    from codeforces_catalog import CodeforcesCatalog
    from codeforces_import import (
        build_problem_payload,
        fetch_problem_html,
        parse_codeforces_problem_html,
    )
    from event_store import EventStore
    from models import (
        CodeforcesImportRequest,
        CodeforcesImportResponse,
        CodeforcesSearchResponse,
        CodeforcesSearchResult,
        CustomProblemDeleteResponse,
        CustomProblemRequest,
        CustomProblemResponse,
        RunCancelResponse,
        RunDeleteResponse,
        RunRequest,
        RunResponse,
        RunSummary,
    )
    from process_runner import ProcessManager
    from ws_manager import WebSocketManager

app = FastAPI(title="AlgoPilot Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ws_manager = WebSocketManager()
event_store = EventStore()
process_manager = ProcessManager()
_codeforces_catalog: CodeforcesCatalog | None = None
CODEFORCES_URL_RE = re.compile(
    r"^https?://(?:www\.)?codeforces\.com/contest/(?P<contest_id>\d+)/problem/(?P<index>[A-Za-z0-9]+)$"
)


def get_codeforces_catalog() -> CodeforcesCatalog:
    global _codeforces_catalog
    if _codeforces_catalog is None:
        _codeforces_catalog = CodeforcesCatalog(CODEFORCES_CACHE_PATH)
    return _codeforces_catalog


def _slugify(value: str, fallback: str = "custom-problem") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or fallback


def _resolve_problem_file(problem_id: str) -> Path:
    safe_name = Path(problem_id).name
    if safe_name != problem_id:
        raise HTTPException(status_code=400, detail="Invalid problem id")
    return PROBLEMS_DIR / safe_name


def _load_problem_content(problem_path: Path) -> dict:
    if not problem_path.exists():
        raise HTTPException(status_code=404, detail="Problem not found")
    return json.loads(problem_path.read_text(encoding="utf-8"))


def _assert_custom_problem(problem_path: Path) -> dict:
    content = _load_problem_content(problem_path)
    meta = content.get("_metadata", {}) or {}
    if not bool(meta.get("custom", False)):
        raise HTTPException(status_code=400, detail="Only custom problems can be modified")
    return content


def _build_custom_problem_payload(
    req: CustomProblemRequest,
    *,
    problem_id_override: str | None = None,
) -> tuple[str, dict]:
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    stem = problem_id_override or f"custom_{timestamp}_{_slugify(req.title)}"
    description = req.description.strip()
    constraints_text = req.constraints_text.strip()
    if constraints_text:
        description = f"{description}\n\nConstraints\n{constraints_text}"

    public_tests = [
        {
            "input": case.input,
            "output": case.output,
        }
        for case in req.public_tests
        if case.input.strip() or case.output.strip()
    ]

    payload = {
        "problem_id": stem,
        "description": description,
        "public_tests": public_tests,
        "constraints": {"raw": constraints_text} if constraints_text else {},
        "time_limit": req.time_limit_ms,
        "space_limit": req.memory_limit_mb,
        "types": [],
        "_metadata": {
            "source": req.source.strip() or "custom",
            "platform": "custom",
            "question_id": stem,
            "name": req.title.strip(),
            "difficulty": req.difficulty if req.difficulty not in ("", None) else "custom",
            "created_at": timestamp,
            "custom": True,
        },
    }
    return stem, payload


def _resolve_codeforces_problem_key(req: CodeforcesImportRequest) -> tuple[int, str]:
    if req.contest_id is not None and req.index:
        return int(req.contest_id), req.index.strip().upper()

    if req.url:
        normalized_url = req.url.strip()
        match = CODEFORCES_URL_RE.match(normalized_url)
        if match is not None:
            return int(match.group("contest_id")), match.group("index").upper()
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported Codeforces problem URL: {normalized_url}",
        )

    raise HTTPException(
        status_code=400,
        detail="Provide contest_id and index, or a valid Codeforces problem URL",
    )


def import_codeforces_problem_payload(req: CodeforcesImportRequest) -> dict:
    contest_id, index = _resolve_codeforces_problem_key(req)
    rating = None
    tags: list[str] = []

    try:
        catalog_rows = get_codeforces_catalog().search(f"{contest_id} {index}", limit=1)
    except Exception:
        catalog_rows = []

    if catalog_rows:
        rating = catalog_rows[0].get("rating")
        tags = list(catalog_rows[0].get("tags", []))

    try:
        html = fetch_problem_html(contest_id, index)
        parsed = parse_codeforces_problem_html(html, contest_id, index)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Failed to fetch Codeforces problem") from exc

    return build_problem_payload(parsed, contest_id, index, rating, tags)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/sources/codeforces/search", response_model=CodeforcesSearchResponse)
async def search_codeforces(q: str, limit: int = 20):
    catalog = get_codeforces_catalog()
    results = [
        CodeforcesSearchResult(**row)
        for row in catalog.search(q, limit=max(1, min(limit, 50)))
    ]
    return CodeforcesSearchResponse(results=results, cache_status="ready")


@app.post("/api/sources/codeforces/import", response_model=CodeforcesImportResponse)
async def import_codeforces_problem(req: CodeforcesImportRequest):
    PROBLEMS_DIR.mkdir(parents=True, exist_ok=True)
    contest_id, index = _resolve_codeforces_problem_key(req)
    problem_id = f"codeforces_{contest_id}_{index}"
    problem_path = PROBLEMS_DIR / f"{problem_id}.json"
    if problem_path.exists():
        payload = _load_problem_content(problem_path)
        return CodeforcesImportResponse(
            problem_id=problem_id,
            filename=problem_path.name,
            problem=payload,
        )

    payload = import_codeforces_problem_payload(req)
    problem_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return CodeforcesImportResponse(
        problem_id=payload["problem_id"],
        filename=problem_path.name,
        problem=payload,
    )


@app.get("/api/dag")
async def get_dag():
    data = json.loads(DAG_DEFINITION_PATH.read_text(encoding="utf-8"))
    return data


@app.get("/api/problems")
async def list_problems():
    if not PROBLEMS_DIR.exists():
        return {"problems": []}
    results = []
    for f in sorted(PROBLEMS_DIR.glob("*.json")):
        try:
            content = json.loads(f.read_text(encoding="utf-8"))
            meta = content.get("_metadata", {})
            desc = content.get("description", "")
            results.append({
                "id": f.name,
                "name": meta.get("name", f.stem.replace("_", " ")),
                "source": meta.get("source", "unknown"),
                "family": meta.get("family", ""),
                "difficulty": meta.get("difficulty", 0),
                "is_custom": bool(meta.get("custom", False)),
                "is_showcase": bool(meta.get("showcase", False)),
                "preview": desc[:120] + ("..." if len(desc) > 120 else ""),
            })
        except Exception:
            continue
    return {"problems": results}


@app.get("/api/problems/{problem_id}")
async def get_problem(problem_id: str):
    problem_file = _resolve_problem_file(problem_id)
    return _load_problem_content(problem_file)


@app.post("/api/problems/custom", response_model=CustomProblemResponse)
async def save_custom_problem(req: CustomProblemRequest):
    PROBLEMS_DIR.mkdir(parents=True, exist_ok=True)
    stem, payload = _build_custom_problem_payload(req)
    problem_path = PROBLEMS_DIR / f"{stem}.json"
    suffix = 1
    while problem_path.exists():
        problem_path = PROBLEMS_DIR / f"{stem}_{suffix}.json"
        payload["problem_id"] = problem_path.stem
        payload["_metadata"]["question_id"] = problem_path.stem
        suffix += 1
    problem_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return CustomProblemResponse(
        problem_id=problem_path.stem,
        filename=problem_path.name,
        problem=payload,
    )


@app.put("/api/problems/custom/{problem_id}", response_model=CustomProblemResponse)
async def update_custom_problem(problem_id: str, req: CustomProblemRequest):
    PROBLEMS_DIR.mkdir(parents=True, exist_ok=True)
    problem_path = _resolve_problem_file(problem_id)
    _assert_custom_problem(problem_path)
    stem = problem_path.stem
    _, payload = _build_custom_problem_payload(req, problem_id_override=stem)
    problem_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return CustomProblemResponse(
        problem_id=stem,
        filename=problem_path.name,
        problem=payload,
    )


@app.delete("/api/problems/custom/{problem_id}", response_model=CustomProblemDeleteResponse)
async def delete_custom_problem(problem_id: str):
    problem_path = _resolve_problem_file(problem_id)
    _assert_custom_problem(problem_path)
    problem_path.unlink(missing_ok=False)
    return CustomProblemDeleteResponse(
        deleted=True,
        filename=problem_path.name,
    )


@app.post("/api/runs", response_model=RunResponse)
async def start_run(req: RunRequest, request: Request):
    proc = process_manager.create_run(problem=req.problem, config=req.config)
    await proc.start(ws_manager, event_store)
    host_header = request.headers.get("host") or request.url.netloc
    ws_scheme = "wss" if request.url.scheme == "https" else "ws"
    return RunResponse(
        run_id=proc.run_id,
        status="running",
        ws_url=f"{ws_scheme}://{host_header}/ws/live/{proc.run_id}",
    )


@app.get("/api/runs")
async def list_runs():
    stored = event_store.list_runs()
    active = []
    for run_id, proc in process_manager._processes.items():
        if proc.status == "running":
            meta = (proc.problem or {}).get("_metadata", {}) if isinstance(proc.problem, dict) else {}
            active.append({
                "run_id": run_id,
                "problem_id": proc.problem_id,
                "problem_name": meta.get("name", proc.problem_id),
                "problem_family": meta.get("family", ""),
                "status": "running",
                "final_status": None,
                "started_at": proc.started_at,
            })
    return {"runs": active + stored}


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str):
    proc = process_manager.get(run_id)
    if proc and proc.status == "running":
        return {
            "run_id": proc.run_id,
            "problem_id": proc.problem_id,
            "problem": proc.problem,
            "config": proc.config,
            "started_at": proc.started_at,
            "completed_at": None,
            "final_status": None,
            "events": proc.events,
        }
    stored = event_store.get_run(run_id)
    if stored:
        return stored
    if proc:
        return {
            "run_id": proc.run_id,
            "problem_id": proc.problem_id,
            "problem": proc.problem,
            "config": proc.config,
            "started_at": proc.started_at,
            "completed_at": proc.completed_at,
            "final_status": proc.final_status or proc.status,
            "events": proc.events,
        }
    raise HTTPException(status_code=404, detail="Run not found")


@app.post("/api/runs/{run_id}/cancel", response_model=RunCancelResponse)
async def cancel_run(run_id: str):
    proc = process_manager.get(run_id)
    if proc is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if proc.status != "running":
        raise HTTPException(status_code=409, detail="Run is not active")

    try:
        final_status = await proc.cancel()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail="Run is not active") from exc
    return RunCancelResponse(
        run_id=run_id,
        cancelled=final_status == "cancelled",
        final_status=final_status,
    )


@app.delete("/api/runs/{run_id}", response_model=RunDeleteResponse)
async def delete_run(run_id: str):
    proc = process_manager.get(run_id)
    if proc is not None and proc.status == "running":
        raise HTTPException(status_code=409, detail="Cannot delete a running run")

    deleted = event_store.delete_run(run_id)
    if not deleted:
        if proc is not None:
            process_manager.release(run_id)
        raise HTTPException(status_code=404, detail="Run not found")

    if proc is not None:
        process_manager.release(run_id)

    return RunDeleteResponse(
        run_id=run_id,
        deleted=True,
    )


@app.websocket("/ws/live/{run_id}")
async def websocket_endpoint(websocket: WebSocket, run_id: str):
    await ws_manager.connect(run_id, websocket)
    buffered = process_manager.get_buffered_events(run_id)
    for event in buffered:
        try:
            await websocket.send_json(event)
        except Exception:
            break
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(run_id, websocket)


def _frontend_index_path() -> Path | None:
    index_path = FRONTEND_DIST_DIR / "index.html"
    if index_path.exists():
        return index_path
    return None


@app.get("/", include_in_schema=False)
async def frontend_index():
    index_path = _frontend_index_path()
    if index_path is None:
        raise HTTPException(status_code=404, detail="Frontend build not found")
    return FileResponse(index_path)


@app.get("/{full_path:path}", include_in_schema=False)
async def frontend_spa(full_path: str):
    if full_path.startswith("api/") or full_path.startswith("ws/"):
        raise HTTPException(status_code=404, detail="Not found")

    index_path = _frontend_index_path()
    if index_path is None:
        raise HTTPException(status_code=404, detail="Frontend build not found")

    candidate = (FRONTEND_DIST_DIR / full_path).resolve()
    try:
        candidate.relative_to(FRONTEND_DIST_DIR.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid frontend path") from exc

    if full_path and candidate.exists() and candidate.is_file():
        return FileResponse(candidate)
    return FileResponse(index_path)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
