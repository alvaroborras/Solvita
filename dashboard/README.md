# AlgoPilot Dashboard Deployment

The AlgoPilot dashboard is designed to be portable across machines and operating systems.
It no longer depends on hard-coded localhost ports at runtime.

## What Changed

- Backend host/port are environment-driven.
- Frontend dev proxy target is environment-driven.
- A portable launcher automatically finds free ports when the preferred ones are occupied.
- In production-style mode, the FastAPI backend serves the built frontend on the same origin, so the UI is decoupled from a fixed Vite port.
- Python interpreter resolution supports:
  - `.venv/bin/python`
  - `.venv/Scripts/python.exe`
  - the current `sys.executable`

## One-Time Setup

From the repository root:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cd dashboard/frontend
npm install
cd ../..
```

On Windows PowerShell:

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt

cd dashboard/frontend
npm install
cd ../..
```

## Recommended Start Command

Production-style single-origin mode:

```bash
python scripts/start_dashboard.py
```

Behavior:

- If `dashboard/frontend/dist` is missing, the launcher builds the frontend automatically.
- If port `8766` is already occupied, it picks a free backend port automatically.
- The launcher prints the final URL to open in your browser.

## Development Mode

If you want live Vite hot reload:

```bash
python scripts/start_dashboard.py --mode dev
```

Behavior:

- Picks a free backend port automatically.
- Picks a free frontend port automatically if `5173` is occupied.
- Configures the Vite proxy through environment variables instead of hard-coded local targets.

## Useful Environment Variables

All of these are optional.

```bash
ALGOPILOT_DASHBOARD_HOST=127.0.0.1
ALGOPILOT_DASHBOARD_PORT=8766
ALGOPILOT_DASHBOARD_FRONTEND_PORT=5173
ALGOPILOT_DASHBOARD_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:4173
ALGOPILOT_DASHBOARD_CORS_ORIGIN_REGEX=https?://(localhost|127\.0\.0\.1)(:\d+)?$
ALGOPILOT_DASHBOARD_FRONTEND_DIST=/absolute/path/to/dist
ALGOPILOT_PROBLEMS_DIR=/absolute/path/to/data/problem
ALGOPILOT_DASHBOARD_DATA_DIR=/absolute/path/to/dashboard/data/runs
ALGOPILOT_PYTHON=/absolute/path/to/python
```

## Manual Commands

Backend only:

```bash
cd dashboard/backend
python server.py
```

Frontend only:

```bash
cd dashboard/frontend
npm run dev
```

If you start them manually, set environment variables first so the two sides agree on ports.

## GitHub-Friendly Usage

For a new machine:

1. Clone the repo.
2. Create a Python virtualenv.
3. `pip install -r requirements.txt`
4. `cd dashboard/frontend && npm install`
5. Run `python scripts/start_dashboard.py`

No source code edits should be required just because a machine uses different ports.

## Codeforces Search and Import

- The problem picker now supports a `Codeforces` tab.

Flow:

1. Open `Start Solve`
2. Select `Codeforces`
3. Search by contest/index (for example `1575 C`) or by title keyword
4. Click `Import and Solve`

Imported problems are written into `data/problem/` as normal local AlgoPilot problem JSON files and then solved through the standard run path.
