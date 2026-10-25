@echo off
rem Local run without Docker: 4 windows (GigaChat proxy, mocks, backend, site).
rem First time: see "Zapusk bez Docker" in README.md (venv for backend, npm install for frontend).
cd /d "%~dp0"
if not exist ".env" (
  echo [!] No .env file. Copy .env.example to .env and fill it. AI will be off.
)
if not exist "frontend\.env.local" copy "frontend\.env.example" "frontend\.env.local" >nul
start "1 gpt2giga" cmd /k "gpt2giga"
start "2 mocks" cmd /k "python mocks\devserver.py"
start "3 backend" cmd /k "backend\run-local.bat"
start "4 frontend" cmd /k "cd frontend && npm run dev"
echo Started. Site: http://localhost:3000   Staff: http://localhost:3000/staff   Health: http://localhost:8000/api/health
