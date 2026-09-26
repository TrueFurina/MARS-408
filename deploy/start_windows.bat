@echo off
chcp 65001 >nul
setlocal EnableExtensions
rem ===================================================================
rem  MARS-408 / study-help-pro  one-click launcher (Windows)
rem
rem  Duty : preflight checks -> start backend (uvicorn main:app) in the
rem         background -> poll health -> print access info.
rem  Rules: never modify existing files, never kill a process that this
rem         script did not start. Any failed preflight prints a readable
rem         remedy and exits with code 2.
rem
rem  Usage:
rem    deploy\start_windows.bat
rem    set PORT=8007 && deploy\start_windows.bat     (if 8002 is taken)
rem
rem  NOTE: all console output is plain ASCII on purpose, so it renders
rem        correctly on a GBK (code page 936) console.
rem ===================================================================

rem ---------- configurable (env vars may override) -------------------
if not defined PORT set "PORT=8002"
if not defined HOST set "HOST=127.0.0.1"
if not defined HEALTH_PATH set "HEALTH_PATH=/api/status"
if not defined STARTUP_TIMEOUT set "STARTUP_TIMEOUT=60"
if not defined POLL_INTERVAL set "POLL_INTERVAL=2"
rem  Version floor comes from the project facts:
rem    py-server/pyproject.toml   requires-python = ">=3.12"
rem    py-server/.python-version  3.12
rem  To tighten it to 3.13+, run:  set PY_MIN_MINOR=13
if not defined PY_MIN_MAJOR set "PY_MIN_MAJOR=3"
if not defined PY_MIN_MINOR set "PY_MIN_MINOR=12"

rem ---------- paths ---------------------------------------------------
for %%I in ("%~dp0.") do set "SCRIPT_DIR=%%~fI"
for %%I in ("%~dp0..") do set "REPO_ROOT=%%~fI"
set "PY_SERVER_DIR=%REPO_ROOT%\py-server"
set "VENV_DIR=%PY_SERVER_DIR%\.venv"
set "MODEL_DIR=%PY_SERVER_DIR%\models\e5-base-v2"
set "LOG_DIR=%SCRIPT_DIR%\logs"
set "LOG_FILE=%LOG_DIR%\backend.log"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo ====================================================================
echo  MARS-408 one-click launcher (backend)
echo  repo   : %REPO_ROOT%
echo  server : %PY_SERVER_DIR%
echo  target : http://%HOST%:%PORT%%HEALTH_PATH%
echo ====================================================================

rem ---------- step 1/6 : python interpreter ---------------------------
echo [INFO ] [1/6] Checking Python interpreter ...
set "PY="
if exist "%VENV_DIR%\Scripts\python.exe" set "PY=%VENV_DIR%\Scripts\python.exe"
if not defined PY if exist "%VENV_DIR%\bin\python.exe" set "PY=%VENV_DIR%\bin\python.exe"
if not defined PY for /f "delims=" %%P in ('where python 2^>nul') do if not defined PY set "PY=%%P"

if not defined PY goto :no_python
echo [ OK  ] Python interpreter: %PY%

for /f "delims=" %%V in ('"%PY%" -c "import sys;print('{}.{}.{}'.format(*sys.version_info[:3]))"') do set "PY_VER=%%V"
"%PY%" -c "import os,sys;maj=int(os.environ['PY_MIN_MAJOR']);mnr=int(os.environ['PY_MIN_MINOR']);sys.exit(0 if sys.version_info[:2]>=(maj,mnr) else 1)"
if errorlevel 1 goto :bad_python_version
echo [ OK  ] Python version %PY_VER% ^>= %PY_MIN_MAJOR%.%PY_MIN_MINOR%

rem ---------- step 2/6 : virtual environment --------------------------
echo [INFO ] [2/6] Checking virtual environment at %VENV_DIR% ...
if not exist "%VENV_DIR%" goto :no_venv
echo [ OK  ] Virtual environment found.

rem ---------- step 3/6 : E5 embedding model ---------------------------
echo [INFO ] [3/6] Checking E5 model at %MODEL_DIR% ...
if not exist "%MODEL_DIR%" goto :no_model
echo [ OK  ] E5 model found.

rem ---------- step 4/6 : port occupancy -------------------------------
echo [INFO ] [4/6] Checking port %PORT% on %HOST% ...
"%PY%" -c "import os,socket,sys;s=socket.socket();s.settimeout(1);rc=s.connect_ex((os.environ['HOST'],int(os.environ['PORT'])));s.close();sys.exit(0 if rc==0 else 1)"
if not errorlevel 1 goto :port_busy
echo [ OK  ] Port %PORT% is free.

rem ---------- step 5/6 : start backend + wait for readiness -----------
echo [INFO ] [5/6] Starting backend: uvicorn main:app --host %HOST% --port %PORT%
echo [INFO ]       working dir : %PY_SERVER_DIR%
echo [INFO ]       log file    : %LOG_FILE%
if exist "%LOG_FILE%" move /Y "%LOG_FILE%" "%LOG_FILE%.old" >nul

cd /d "%PY_SERVER_DIR%"
rem --workers 1 is mandatory: main.py enforces a single-writer lock on
rem py-server\vectordb_data\.import_writer.lock and refuses to boot with >1 worker.
start "MARS-408-Backend" /B cmd /c ""%PY%" -m uvicorn main:app --host %HOST% --port %PORT% --workers 1 > "%LOG_FILE%" 2>&1"
echo [ OK  ] Backend process started in background.
echo [INFO ]       waiting for readiness (timeout %STARTUP_TIMEOUT%s, first boot ~30s) ...

set "ELAPSED=0"
if not defined POLL_INTERVAL set "POLL_INTERVAL=2"

:wait_loop
if %ELAPSED% GEQ %STARTUP_TIMEOUT% goto :wait_timeout
"%PY%" -c "import os,sys,urllib.request;u='http://'+os.environ['HOST']+':'+os.environ['PORT']+os.environ['HEALTH_PATH'];r=urllib.request.urlopen(u,timeout=3);sys.exit(0 if r.status==200 else 1)"
if not errorlevel 1 goto :ready
<nul set /p "."
timeout /t %POLL_INTERVAL% /nobreak >nul
set /a ELAPSED+=POLL_INTERVAL
goto :wait_loop

rem ---------- step 6/6 : success --------------------------------------
:ready
echo.
echo ====================================================================
echo [ OK  ] [6/6] Backend is UP.
echo.
echo   Backend URL    : http://%HOST%:%PORT%
echo   Health probe   : http://%HOST%:%PORT%%HEALTH_PATH%
echo   API docs       : http://%HOST%:%PORT%/docs
echo   Log file       : %LOG_FILE%
echo.
echo   Tail log       : type "%LOG_FILE%"
echo   Stop backend   : netstat -ano ^| findstr :%PORT%
echo                    then: taskkill /PID ^<pid from last column^> /F
echo.
echo   Frontend (run in ANOTHER terminal, from repo root %REPO_ROOT%):
echo     npm install          (first time only)
echo     npm run dev          (vite dev server)
echo     npm run preview      (serve the prebuilt dist/)
echo ====================================================================
endlocal
exit /b 0

rem ---------- failure branches ----------------------------------------
:no_python
echo [FAIL ] No Python interpreter found. 1>&2
echo [FAIL ]   Install Python ^>= %PY_MIN_MAJOR%.%PY_MIN_MINOR% first: 1>&2
echo [FAIL ]     winget install -e --id Python.Python.3.12 1>&2
echo [FAIL ]     or download from https://www.python.org/downloads/ 1>&2
echo [FAIL ]   Then create the venv (see next hint) and re-run. 1>&2
endlocal
exit /b 2

:bad_python_version
echo [FAIL ] Python version %PY_VER% is too old (need ^>= %PY_MIN_MAJOR%.%PY_MIN_MINOR%). 1>&2
echo [FAIL ]   Install Python %PY_MIN_MAJOR%.%PY_MIN_MINOR%+ and rebuild the venv: 1>&2
echo [FAIL ]     cd py-server ^&^& uv sync --frozen 1>&2
echo [FAIL ]   (uv not installed?  winget install -e --id astral-sh.uv ) 1>&2
endlocal
exit /b 2

:no_venv
echo [FAIL ] Virtual environment not found: %VENV_DIR% 1>&2
echo [FAIL ]   Please create it first (pick ONE): 1>&2
echo [FAIL ]     A. uv (authoritative, uses uv.lock): 1>&2
echo [FAIL ]          cd py-server ^&^& uv sync --frozen 1>&2
echo [FAIL ]     B. plain venv + pip: 1>&2
echo [FAIL ]          cd py-server ^&^& python -m venv .venv 1>&2
echo [FAIL ]          cd py-server ^&^& .venv\Scripts\python.exe -m pip install -e . 1>&2
echo [FAIL ]   If 'uv' is missing:  winget install -e --id astral-sh.uv 1>&2
endlocal
exit /b 2

:no_model
echo [FAIL ] Embedding model not found: %MODEL_DIR% 1>&2
echo [FAIL ]   intfloat/e5-base-v2 (768-dim) is NOT in version control. 1>&2
echo [FAIL ]   Please fetch it once (run from the py-server directory): 1>&2
echo [FAIL ]     cd py-server ^&^& %PY% ..\scripts\fetch_e5_model.py 1>&2
echo [FAIL ]   Note: fetch_e5_model.py lives in the repo-root scripts\ dir. 1>&2
endlocal
exit /b 2

:port_busy
echo [FAIL ] Port %PORT% is ALREADY IN USE. 1>&2
echo [FAIL ]   This script will NOT kill someone else's process. 1>&2
echo [FAIL ]   Find who owns it: 1>&2
echo [FAIL ]     netstat -ano ^| findstr :%PORT%      (last column = PID) 1>&2
echo [FAIL ]     tasklist /FI "PID eq ^<pid^>" 1>&2
echo [FAIL ]   Then either stop that process yourself, or use another port: 1>&2
echo [FAIL ]     set PORT=8007 ^&^& deploy\start_windows.bat 1>&2
endlocal
exit /b 2

:wait_timeout
echo. 1>&2
echo [FAIL ] Backend did not become ready within %STARTUP_TIMEOUT% seconds. 1>&2
echo [FAIL ]   ---- last lines of %LOG_FILE% ---- 1>&2
type "%LOG_FILE%" 1>&2
echo [FAIL ]   ---- how to stop it ---- 1>&2
echo [FAIL ]     netstat -ano ^| findstr :%PORT% 1>&2
echo [FAIL ]     taskkill /PID ^<pid^> /F 1>&2
endlocal
exit /b 2
