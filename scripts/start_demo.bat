@echo off
REM ============================================================
REM MARS-408 one-click demo launcher (Windows)
REM Starts backend (uvicorn, workers=1) + frontend (vite),
REM waits for backend health, then opens the browser.
REM
REM NOTE: backend cold start loads 2083 vectors + E5 (~30s).
REM The health probe uses curl -m 30 to tolerate slow boot.
REM Do NOT add --workers N (single-process lock enforced).
REM ============================================================

setlocal
set ROOT=%~dp0..
set BACKEND=%ROOT%\py-server
set VENV=%BACKEND%\.venv\Scripts\python.exe
set BACKEND_URL=http://127.0.0.1:8002
set FRONTEND_URL=http://localhost:5173

REM --- 1) start backend in its own window ---
if not exist "%VENV%" (
    echo [ERR] venv not found at %VENV%. Run: cd py-server && python -m venv .venv && .venv\Scripts\pip install -r requirements.txt
    goto end
)
start "MARS-408-backend" cmd /k "cd /d %BACKEND% && %VENV% -m uvicorn main:app --host 127.0.0.1 --port 8002 --workers 1"

REM --- 2) wait for backend health (cold start ~30s) ---
echo Waiting for backend health at %BACKEND_URL%/api/status ...
set /a tries=0
:healthloop
curl -m 30 -s -o nul -w "%%{http_code}" %BACKEND_URL%/api/status 2>nul | findstr /r "^[0-9][0-9][0-9]$" >nul
if not errorlevel 1 goto backend_up
timeout /t 3 >nul
set /a tries+=1
if %tries% lss 20 goto healthloop
echo [WARN] backend health probe timed out after ~60s. Check py-server window / backend_run.log.
goto frontend

:backend_up
echo Backend is UP.

:frontend
REM --- 3) start frontend in its own window ---
start "MARS-408-frontend" cmd /k "cd /d %ROOT% && npm run dev"

REM --- 4) wait a moment, then open browser ---
timeout /t 6 >nul
echo Opening %FRONTEND_URL% ...
start "" %FRONTEND_URL%

:end
echo Demo environment launched. Close the two cmd windows to stop.
endlocal
