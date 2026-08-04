$ErrorActionPreference = "Continue"
Set-Location "C:\Users\actsl.DESKTOP-5CTNC21\OneDrive\Documents\Desktop\mlb-predictor\backend"
$logFile = "data_cache\daily_retrain_run.log"
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path $logFile -Value "=== Run started $timestamp ==="
& ".\venv\Scripts\python.exe" "daily_retrain.py" *>> $logFile
Add-Content -Path $logFile -Value "=== Run finished $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') exit code $LASTEXITCODE ==="
