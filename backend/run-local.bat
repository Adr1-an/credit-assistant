@echo off
rem Backend without Docker. Settings are read from ..\.env, local addresses are set below.
cd /d "%~dp0"
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"
if exist "..\.env" for /f "usebackq eol=# tokens=1,* delims==" %%a in ("..\.env") do set "%%a=%%b"
set "DATABASE_URL=sqlite:///./app.db"
set "MOCKS_URL=http://localhost:8090"
set "EVALUATION_DATE=2026-10-24"
set "LLM_BASE_URL=http://localhost:8091/v1"
echo LLM_ENABLED=%LLM_ENABLED%
python -m uvicorn app.main:app --port 8000
