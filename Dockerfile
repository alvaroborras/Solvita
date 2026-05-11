# ─── Solvita — Linux test image ──────────────────────────────────────────────
# Includes: Python 3.12, g++17, Node.js 20, Python deps, CLI build
# Usage:  docker build -t solvita .
#         docker run -it --rm solvita

FROM python:3.12-slim

# ── System packages ────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        # C++ compilation (rlimit sandbox runs fully on Linux)
        g++ \
        build-essential \
        # For downloading Node.js setup script
        curl \
        ca-certificates \
    && \
    # ── Node.js 20 LTS ────────────────────────────────────────────────────────
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    # ── Cleanup ───────────────────────────────────────────────────────────────
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Python dependencies (install before copying code for layer caching) ────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Project source ─────────────────────────────────────────────────────────────
COPY . .

# ── Node.js CLI: install deps + compile TypeScript ────────────────────────────
WORKDIR /app/cli
RUN npm ci --prefer-offline 2>/dev/null || npm install
RUN npm run build

WORKDIR /app

# ── Smoke test: confirm key binaries exist ─────────────────────────────────────
RUN python --version && \
    g++ --version | head -1 && \
    node --version && \
    node cli/bin/solvita.js --version

# ── Default: interactive bash so the user can run any command ─────────────────
CMD ["/bin/bash"]
