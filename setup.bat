@echo off
REM One-time setup. Double-click this file.
REM Installs everything and trains the initial model. Takes 20-40 minutes
REM (mostly waiting on MLB's API while it pulls a few seasons of history).

cd /d "%~dp0"

echo ==================================================
echo  Matchup Edge - first-time setup
echo ==================================================

where python >nul 2>nul
if errorlevel 1 (
    echo Python not found. Install it from https://python.org and re-run this.
    echo IMPORTANT: during install, check "Add python.exe to PATH".
    pause
    exit /b 1
)

echo.
echo [1/5] Creating Python virtual environment...
cd backend
python -m venv venv
call venv\Scripts\activate.bat

echo.
echo [2/5] Installing Python packages...
pip install --upgrade pip -q
pip install -r requirements.txt -q

echo.
echo [3/5] Pulling historical game data (2025-2026). This is the slow part - grab a coffee...
python build_training_data.py --seasons 2025 2026

echo.
echo [4/5] Training the model and running backtest...
python train.py

call venv\Scripts\deactivate.bat
cd ..\frontend

echo.
echo [5/5] Installing dashboard packages...
where npm >nul 2>nul
if errorlevel 1 (
    echo Node.js/npm not found. Install it from https://nodejs.org, then re-run this script.
    pause
    exit /b 1
)
call npm install --silent

echo.
echo ==================================================
echo  Setup complete! Double-click start.bat any time to launch.
echo ==================================================
pause
