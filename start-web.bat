@echo off
REM ============================================================
REM  Traffic Analysis — One-click Web Server (Windows)
REM  Khởi động server web tại http://localhost:8000
REM ============================================================
setlocal EnableDelayedExpansion
title Traffic Analysis — Web Server
set "ROOT=%~dp0"
cd /d "%ROOT%"

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║   Traffic Analysis — Web Server          ║
echo  ╚══════════════════════════════════════════╝
echo.

REM ── 1. Xác định Python ──────────────────────────────────────
set "PYTHON="
if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
) else (
    where python >nul 2>&1
    if !errorlevel! equ 0 (
        set "PYTHON=python"
    )
)
if "%PYTHON%"=="" (
    echo [ERROR] Khong tim thay Python. Cai dat Python 3.10+ roi chay lai.
    pause
    exit /b 1
)

REM Kiểm tra version
"%PYTHON%" --version 2>&1
echo.

REM ── 2. Tạo venv nếu chưa có ────────────────────────────────
if not exist ".venv\Scripts\python.exe" (
    echo [1/4] Tao virtual environment...
    python -m venv .venv
    if !errorlevel! neq 0 (
        echo [ERROR] Khong tao duoc venv.
        pause
        exit /b 1
    )
    set "PYTHON=.venv\Scripts\python.exe"
    echo       Done.
) else (
    echo [1/4] Virtual environment: OK
)

REM ── 3. Cài Python deps ──────────────────────────────────────
echo [2/4] Kiem tra Python dependencies...
"%PYTHON%" -c "import fastapi; import uvicorn; import supervision" >nul 2>&1
if !errorlevel! neq 0 (
    echo       Cai dat dependencies tu requirements-prod.txt...
    "%PYTHON%" -m pip install --quiet --upgrade pip
    "%PYTHON%" -m pip install --quiet -r requirements-prod.txt
    if !errorlevel! neq 0 (
        echo [ERROR] Cai dat dependencies that bai.
        pause
        exit /b 1
    )
    echo       Done.
) else (
    echo       Dependencies: OK
)

REM ── 4. Build frontend (nếu cần) ────────────────────────────
if exist "frontend\dist\index.html" (
    echo [3/4] Frontend build: OK ^(da co san^)
) else (
    echo [3/4] Build frontend...
    where node >nul 2>&1
    if !errorlevel! neq 0 (
        echo [WARN] Node.js khong co. Bo qua build frontend.
        echo        Cai Node.js 18+ de build, hoac copy thu muc frontend\dist\ tu may khac.
    ) else (
        pushd frontend
        if not exist "node_modules" (
            echo       npm install...
            call npm ci --silent
        )
        echo       npm run build...
        call npm run build
        if !errorlevel! neq 0 (
            echo [ERROR] Build frontend that bai.
            popd
            pause
            exit /b 1
        )
        popd
        echo       Done.
    )
)

REM ── 5. Khởi động server ─────────────────────────────────────
set "PORT=8000"
if not "%1"=="" set "PORT=%1"

echo [4/4] Khoi dong server tai http://localhost:!PORT!
echo.
echo  ────────────────────────────────────────────
echo   URL:  http://localhost:!PORT!
echo   Stop: Ctrl+C
echo  ────────────────────────────────────────────
echo.

REM Mở browser sau 2 giây
start "" /B cmd /c "ping -n 3 localhost >nul 2>&1 & start http://localhost:!PORT!"

"%PYTHON%" -m uvicorn src.adapters.input.web.app:create_app ^
    --factory --host 0.0.0.0 --port !PORT! --workers 1

endlocal
