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

rem Fixed port so the URL matches what's registered as an Authorized
rem JavaScript origin for Google Sign-In (Google requires an exact
rem host+port match, so this can't float). :stop_servers above already
rem frees this port from any previous run of this app.
set "API_PORT=8000"

"%PYTHON%" -X utf8 -c "import dotenv, fastapi, openai, yaml, langchain_chroma, langchain_community, langchain_text_splitters, pypdf, docx2txt, pdf2docx" >nul 2>&1
if errorlevel 1 (
  echo Missing Python dependencies in backend\researcher_crew\.venv.
  echo Run:
  echo   backend\researcher_crew\.venv\Scripts\python -m pip install -r requirements.txt
  goto :fail
)

rem Analytics uses PostgreSQL when DATABASE_BACKEND=postgres. Keep these
rem pinned runtime packages in the exact venv used below, not whichever
rem global Python happens to be first on PATH.
"%PYTHON%" -X utf8 -c "import sqlalchemy, psycopg, alembic" >nul 2>&1
if errorlevel 1 (
  echo PostgreSQL runtime dependencies are missing. Installing pinned versions...
  "%PYTHON%" -X utf8 -m pip install --disable-pip-version-check "SQLAlchemy==2.0.36" "psycopg[binary]==3.2.3" "alembic==1.14.0"
  if errorlevel 1 (
    echo Failed to install PostgreSQL runtime dependencies.
    echo Run manually:
    echo   backend\researcher_crew\.venv\Scripts\python -m pip install -r requirements.txt
    goto :fail
  )
)

call :ensure_database
if errorlevel 1 (
  echo.
  echo Database preflight failed. FastAPI was not started.
  echo Start Docker Desktop, then retry run.bat.
  echo To apply missing migrations manually:
  echo   backend\researcher_crew\.venv\Scripts\python -m alembic -c backend\db\alembic.ini upgrade head
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
start "" "http://localhost:%API_PORT%"

echo.
echo Starting FastAPI app in this terminal.
echo - App: http://localhost:%API_PORT%
echo - Press Ctrl+C to stop the server.
echo.
"%PYTHON%" -X utf8 -m uvicorn backend.api.main:app --host localhost --port %API_PORT% --timeout-keep-alive 1 --timeout-graceful-shutdown 3 --no-access-log
set "APP_EXIT=%ERRORLEVEL%"
endlocal & exit /b %APP_EXIT%

:ensure_database
"%PYTHON%" -X utf8 -m backend.scripts.storage_status database >nul 2>&1
if not errorlevel 1 (
  "%PYTHON%" -X utf8 -m backend.scripts.storage_status database
  exit /b 0
)

where docker >nul 2>&1
if errorlevel 1 (
  "%PYTHON%" -X utf8 -m backend.scripts.storage_status database
  exit /b 1
)

echo PostgreSQL is not ready. Starting the local development database...
set "COMPOSE_DISABLE_ENV_FILE=1"
docker compose -f docker-compose.dev-db.yml up -d
if errorlevel 1 (
  "%PYTHON%" -X utf8 -m backend.scripts.storage_status database
  exit /b 1
)

for /l %%I in (1,1,15) do (
  "%PYTHON%" -X utf8 -m backend.scripts.storage_status database >nul 2>&1
  if not errorlevel 1 (
    "%PYTHON%" -X utf8 -m backend.scripts.storage_status database
    exit /b 0
  )
  timeout /t 1 /nobreak >nul
)

"%PYTHON%" -X utf8 -m backend.scripts.storage_status database
exit /b 1

:stop_servers
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root = (Get-Location).Path; " ^
  "$patterns = 'uvicorn|backend\.api\.main|run\.bat.+__api'; " ^
  "$targets = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.ProcessId -ne $PID -and $_.CommandLine.Contains($root) -and ($_.CommandLine -match $patterns) }; " ^
  "foreach ($target in $targets) { taskkill /PID $target.ProcessId /T /F | Out-Null }" >nul 2>&1
exit /b 0

:fail
endlocal & exit /b 1
