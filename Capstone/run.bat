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
set "OLLAMA_KEEP_ALIVE=1h"

call :stop_servers
call :ensure_ollama
if errorlevel 1 goto :fail

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

:ensure_ollama
for /f "usebackq delims=" %%R in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$running = Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue; if ($running) { '1' }"`) do (
  set "OLLAMA_RUNNING=%%R"
)
if defined OLLAMA_RUNNING (
  echo Ollama sudah berjalan di 127.0.0.1:11434.
  echo Keep-alive akan mengikuti proses Ollama yang sedang aktif.
  exit /b 0
)

where ollama >nul 2>&1
if errorlevel 1 (
  echo Ollama tidak ditemukan di PATH.
  echo Jalankan Ollama secara manual atau tambahkan ke PATH terlebih dahulu.
  exit /b 1
)

echo Menjalankan Ollama dengan OLLAMA_KEEP_ALIVE=%OLLAMA_KEEP_ALIVE%...
start "Capstone Ollama" /min cmd /c "set OLLAMA_KEEP_ALIVE=%OLLAMA_KEEP_ALIVE%&& ollama serve"

set "OLLAMA_READY="
for /l %%I in (1,1,30) do (
  for /f "usebackq delims=" %%R in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$running = Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue; if ($running) { '1' }"`) do (
    set "OLLAMA_READY=%%R"
  )
  if defined OLLAMA_READY goto :ollama_ready
  timeout /t 1 >nul
)

echo Ollama belum merespons di port 11434 setelah 30 detik.
exit /b 1

:ollama_ready
echo Ollama siap di 127.0.0.1:11434.
exit /b 0

:stop_servers
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root = (Get-Location).Path; " ^
  "$patterns = 'uvicorn|backend\.api\.main|run\.bat.+__api'; " ^
  "$targets = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.ProcessId -ne $PID -and $_.CommandLine.Contains($root) -and ($_.CommandLine -match $patterns) }; " ^
  "foreach ($target in $targets) { taskkill /PID $target.ProcessId /T /F | Out-Null }" >nul 2>&1
exit /b 0

:fail
endlocal & exit /b 1
