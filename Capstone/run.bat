@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"
set "ROOT=%CD%"
set "PYTHON=%ROOT%\backend\researcher_crew\.venv\Scripts\python.exe"

if /I "%~1"=="__api" goto :run_api
if /I "%~1"=="__ui" goto :run_ui

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

set "UI_PORT="
for /f "usebackq delims=" %%P in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$port = 8501; while ($port -lt 9000) { $busy = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue; if (-not $busy) { $port; exit 0 }; $port++ }; exit 1"`) do (
  set "UI_PORT=%%P"
)
if not defined UI_PORT (
  echo Could not find a free UI port starting from 8501.
  goto :fail
)

"%PYTHON%" -X utf8 -c "import crewai, dotenv, fastapi, requests, streamlit, yaml, langchain_chroma, langchain_community, langchain_text_splitters, langchain_ollama, pypdf, docx2txt" >nul 2>&1
if errorlevel 1 (
  echo Missing Python dependencies in backend\researcher_crew\.venv.
  echo Run:
  echo   backend\researcher_crew\.venv\Scripts\python -m pip install -r requirements.txt
  goto :fail
)

set "HAS_DB="
for /f "delims=" %%F in ('dir /b /a "backend\chroma_db" 2^>nul') do (
  if /I not "%%F"==".gitkeep" set "HAS_DB=1"
)

if not defined HAS_DB (
  set "HAS_SOURCE_DOCS="
  for /f "delims=" %%F in ('dir /b /s "backend\data\*.pdf" "backend\data\*.docx" "backend\data\*.txt" 2^>nul') do (
    set "HAS_SOURCE_DOCS=1"
  )
  if not defined HAS_SOURCE_DOCS (
    echo No vector DB found, and no PDF, DOCX, or TXT files were found in backend\data.
    echo Add your source documents first, then run this script again.
    goto :fail
  )
  echo No vector DB found. Running ingestion first...
  "%PYTHON%" -X utf8 -m backend.preprocessing.ingest
  if errorlevel 1 goto :fail
) else (
  echo Existing vector DB found. Skipping ingestion.
)

echo Starting API on http://127.0.0.1:%API_PORT%
start "Capstone API" /D "%ROOT%" "%COMSPEC%" /k ""%~f0" __api "%API_PORT%""

echo Starting Streamlit UI on http://127.0.0.1:%UI_PORT%
start "Capstone UI" /D "%ROOT%" "%COMSPEC%" /k ""%~f0" __ui "%API_PORT%" "%UI_PORT%""

echo.
echo App launch requested.
echo - API: http://127.0.0.1:%API_PORT%
echo - UI:  http://127.0.0.1:%UI_PORT%
goto :success

:stop_servers
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root = (Get-Location).Path; " ^
  "$patterns = 'uvicorn|streamlit|backend\.api\.main|frontend[/\\]app\.py|run\.bat.+__(api|ui)'; " ^
  "$targets = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.ProcessId -ne $PID -and $_.CommandLine.Contains($root) -and ($_.CommandLine -match $patterns) }; " ^
  "foreach ($target in $targets) { taskkill /PID $target.ProcessId /T /F | Out-Null }" >nul 2>&1
exit /b 0

:fail
endlocal & exit /b 1

:success
endlocal & exit /b 0

:run_api
set "API_PORT=%~2"
if "%API_PORT%"=="" set "API_PORT=8000"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8="
"%PYTHON%" -X utf8 -m uvicorn backend.api.main:app --host 127.0.0.1 --port %API_PORT%
echo.
echo API server stopped. Press any key to close this window.
pause >nul
endlocal & exit /b 0

:run_ui
set "API_PORT=%~2"
set "UI_PORT=%~3"
if "%API_PORT%"=="" set "API_PORT=8000"
if "%UI_PORT%"=="" set "UI_PORT=8501"
set "API_URL=http://127.0.0.1:%API_PORT%/query"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8="
"%PYTHON%" -X utf8 -m streamlit run frontend/app.py --server.headless true --server.port %UI_PORT%
echo.
echo UI server stopped. Press any key to close this window.
pause >nul
endlocal & exit /b 0
