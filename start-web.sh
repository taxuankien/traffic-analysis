#!/usr/bin/env bash
# ============================================================
#  Traffic Analysis — One-click Web Server (Linux / macOS)
#  Khởi động server web tại http://localhost:8000
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   Traffic Analysis — Web Server          ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── 1. Xác định Python ──────────────────────────────────────
PYTHON=""
if [ -x ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON="python3"
elif command -v python &>/dev/null; then
    PYTHON="python"
fi

if [ -z "$PYTHON" ]; then
    echo "[ERROR] Không tìm thấy Python. Cài đặt Python 3.10+ rồi chạy lại."
    exit 1
fi

$PYTHON --version
echo ""

# ── 2. Tạo venv nếu chưa có ────────────────────────────────
if [ ! -x ".venv/bin/python" ]; then
    echo "[1/4] Tạo virtual environment..."
    $PYTHON -m venv .venv
    PYTHON=".venv/bin/python"
    echo "      Done."
else
    echo "[1/4] Virtual environment: OK"
    PYTHON=".venv/bin/python"
fi

# ── 3. Cài Python deps ──────────────────────────────────────
echo "[2/4] Kiểm tra Python dependencies..."
if ! $PYTHON -c "import fastapi; import uvicorn; import supervision" 2>/dev/null; then
    echo "      Cài đặt dependencies từ requirements-prod.txt..."
    $PYTHON -m pip install --quiet --upgrade pip
    $PYTHON -m pip install --quiet -r requirements-prod.txt
    echo "      Done."
else
    echo "      Dependencies: OK"
fi

# ── 4. Build frontend (nếu cần) ─────────────────────────────
if [ -f "frontend/dist/index.html" ]; then
    echo "[3/4] Frontend build: OK (đã có sẵn)"
else
    echo "[3/4] Build frontend..."
    if ! command -v node &>/dev/null; then
        echo "[WARN] Node.js không có. Bỏ qua build frontend."
        echo "       Cài Node.js 18+ để build, hoặc copy thư mục frontend/dist/ từ máy khác."
    else
        pushd frontend >/dev/null
        if [ ! -d "node_modules" ]; then
            echo "      npm install..."
            npm ci --silent
        fi
        echo "      npm run build..."
        npm run build
        popd >/dev/null
        echo "      Done."
    fi
fi

# ── 5. Khởi động server ─────────────────────────────────────
PORT="${1:-8000}"

echo "[4/4] Khởi động server tại http://localhost:$PORT"
echo ""
echo "────────────────────────────────────────────"
echo " URL:  http://localhost:$PORT"
echo " Stop: Ctrl+C"
echo "────────────────────────────────────────────"
echo ""

# Mở browser sau 2 giây (nền)
(sleep 2 && {
    if command -v xdg-open &>/dev/null; then
        xdg-open "http://localhost:$PORT" 2>/dev/null
    elif command -v open &>/dev/null; then
        open "http://localhost:$PORT"
    fi
}) &

exec $PYTHON -m uvicorn src.adapters.input.web.app:create_app \
    --factory --host 0.0.0.0 --port "$PORT" --workers 1
