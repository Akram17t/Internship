@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"

for %%P in (8000) do (
  for /f "tokens=5" %%I in ('netstat -ano ^| findstr /R /C:":%%P .*LISTENING"') do (
    taskkill /PID %%I /T /F >nul 2>&1
  )
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root = (Get-Location).Path; " ^
  "$patterns = 'uvicorn|backend\.api\.main|run\.bat.+__api'; " ^
  "$targets = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.ProcessId -ne $PID -and $_.CommandLine.Contains($root) -and ($_.CommandLine -match $patterns) }; " ^
  "foreach ($target in $targets) { taskkill /PID $target.ProcessId /T /F 2>$null | Out-Null }; " ^
  "Get-ChildItem -Path . -Recurse -Directory -Force | Where-Object { $_.Name -in @('__pycache__','.pytest_cache') } | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue; " ^
  "Get-ChildItem -Path . -Recurse -File -Filter *.pyc -Force | Remove-Item -Force -ErrorAction SilentlyContinue; " ^
  "Get-ChildItem -Path 'backend\chroma_db' -Force -ErrorAction SilentlyContinue | Where-Object { $_.Name -ne '.gitkeep' } | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue; " ^
  "Write-Host 'Clean complete.'"

if errorlevel 1 exit /b 1
exit /b 0
