@echo off
REM Launch the desktop GUI on Windows.
setlocal
set "ROOT=%~dp0"
cd /d "%ROOT%"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m src.adapters.input.gui.app %*
) else (
    python -m src.adapters.input.gui.app %*
)
endlocal
