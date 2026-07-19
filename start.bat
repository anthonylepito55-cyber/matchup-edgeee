@echo off
REM Daily launcher. Double-click this file.
REM Starts the API and dashboard in their own windows and opens your browser.

cd /d "%~dp0"

if not exist "backend\venv" (
    echo Setup hasn't been run yet. Run setup.bat first ^(one-time, ~20-40 min^).
    pause
    exit /b 1
)

echo Starting backend...
start "Matchup Edge - API" cmd /k "cd backend && call venv\Scripts\activate.bat && uvicorn main:app --port 8000"

echo Starting dashboard...
start "Matchup Edge - Dashboard" cmd /k "cd frontend && npm run dev"

echo Waiting for servers to come up...
timeout /t 5 /nobreak >nul

start http://localhost:5173

echo.
echo ==================================================
echo  Matchup Edge is running in two separate windows.
echo  Dashboard: http://localhost:5173
echo  API:       http://localhost:8000/docs
echo.
echo  Close those two windows to stop everything.
echo ==================================================
pause
