@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"
set "ROOT=%CD%"
set "PYTHON=%ROOT%\backend\researcher_crew\.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
  echo Missing Python environment:
  echo   %PYTHON%
  echo.
  echo Please create or sync the venv in backend\researcher_crew first.
  goto :fail
)

set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8="

call :stop_servers

set "API_PORT="
for /f "usebackq delims=" %%P in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$port = 8000; while ($port -lt 9000) { $busy = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue; if (-not $busy) { $port; exit 0 }; $port++ }; exit 1"`) do (
  set "API_PORT=%%P"
)
if not defined API_PORT (
  echo Could not find a free API port starting from 8000.
  goto :fail
)

"%PYTHON%" -X utf8 -c "import crewai, dotenv, fastapi, yaml, langchain_chroma, langchain_community, langchain_text_splitters, langchain_ollama, pypdf, docx2txt" >nul 2>&1
if errorlevel 1 (
  echo Missing Python dependencies in backend\researcher_crew\.venv.
  echo Run:
  echo   backend\researcher_crew\.venv\Scripts\python -m pip install -r requirements.txt
  goto :fail
)

"%PYTHON%" -X utf8 -m backend.scripts.storage_status vector-db >nul 2>&1
if errorlevel 1 (
  set "HAS_DB="
) else (
  set "HAS_DB=1"
)

if not defined HAS_DB (
  "%PYTHON%" -X utf8 -m backend.scripts.storage_status source-docs >nul 2>&1
  if errorlevel 1 (
    set "HAS_SOURCE_DOCS="
  ) else (
    set "HAS_SOURCE_DOCS=1"
  )
  if not defined HAS_SOURCE_DOCS (
    echo Warning: no vector DB or source documents were found.
    echo The frontend will still open, but AI queries need documents in DATA_DIR.
  ) else (
    echo No valid vector DB found. Running ingestion first...
    "%PYTHON%" -X utf8 -m backend.preprocessing.ingest
    if errorlevel 1 goto :fail
  )
) else (
  echo Existing vector DB found. Skipping ingestion.
)

echo Opening frontend in your browser...
start "" "http://127.0.0.1:%API_PORT%"

echo.
echo Starting FastAPI app in this terminal.
echo - App: http://127.0.0.1:%API_PORT%
echo - Press Ctrl+C to stop the server.
echo.
"%PYTHON%" -X utf8 -m uvicorn backend.api.main:app --host 127.0.0.1 --port %API_PORT% --timeout-keep-alive 1 --timeout-graceful-shutdown 3
set "APP_EXIT=%ERRORLEVEL%"
endlocal & exit /b %APP_EXIT%

:stop_servers
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root = (Get-Location).Path; " ^
  "$patterns = 'uvicorn|backend\.api\.main|run\.bat.+__api'; " ^
  "$targets = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.ProcessId -ne $PID -and $_.CommandLine.Contains($root) -and ($_.CommandLine -match $patterns) }; " ^
  "foreach ($target in $targets) { taskkill /PID $target.ProcessId /T /F | Out-Null }" >nul 2>&1
exit /b 0

:fail
endlocal & exit /b 1
