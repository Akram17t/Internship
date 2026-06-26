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

call :check_port 8000 API
if errorlevel 1 goto :fail

call :check_port 8501 Streamlit
if errorlevel 1 goto :fail

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

echo Starting API on http://127.0.0.1:8000
start "Capstone API" cmd /k "cd /d ""%ROOT%"" && set ""PYTHONIOENCODING=utf-8"" && set ""PYTHONUTF8="" && ""%PYTHON%"" -X utf8 -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8000"

echo Starting Streamlit UI on http://127.0.0.1:8501
start "Capstone UI" cmd /k "cd /d ""%ROOT%"" && set ""PYTHONIOENCODING=utf-8"" && set ""PYTHONUTF8="" && ""%PYTHON%"" -X utf8 -m streamlit run frontend/app.py --server.headless true --server.port 8501"

echo.
echo App launch requested.
echo - API: http://127.0.0.1:8000
echo - UI:  http://127.0.0.1:8501
goto :success

:check_port
set "PORT_PID="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%~1 .*LISTENING"') do (
  set "PORT_PID=%%P"
  goto :port_found
)
goto :eof

:port_found
set "TASKLINE="
for /f "usebackq delims=" %%T in (`tasklist /FI "PID eq !PORT_PID!" /FO CSV /NH`) do (
  set "TASKLINE=%%~T"
)
if /I "!TASKLINE!"=="INFO: No tasks are running which match the specified criteria." (
  echo Ignoring stale port record for %~1 with ghost PID !PORT_PID!.
  exit /b 0
)
echo %~2 port %~1 is already in use by PID !PORT_PID!.
echo Close that process first, then run this script again.
exit /b 1

:fail
endlocal & exit /b 1

:success
endlocal & exit /b 0
