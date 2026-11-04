@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "ROOT=%~dp0"
for %%I in ("%ROOT%.") do set "ROOT=%%~fI"
set "BACKEND_PORT=17608"
set "FRONTEND_PORT=18094"
set "BACKEND_URL=http://127.0.0.1:%BACKEND_PORT%"
set "FRONTEND_URL=https://www.nstl.gov.cn:%FRONTEND_PORT%/ai/agent/claim_consistency/"

cd /d "%ROOT%"

echo ============================================
echo   Claim Consistency Agent - local dev start
echo ============================================
echo.

echo [1/5] Checking project files...
if not exist "%ROOT%\backend\app\main.py" (
    echo [ERROR] Missing backend entry: %ROOT%\backend\app\main.py
    goto :Fail
)
if not exist "%ROOT%\frontend\web\package.json" (
    echo [ERROR] Missing frontend entry: %ROOT%\frontend\web\package.json
    goto :Fail
)

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] python was not found. Install Python 3.11+ and add it to PATH.
    goto :Fail
)

where npm >nul 2>nul
if errorlevel 1 (
    echo [ERROR] npm was not found. Install Node.js and add it to PATH.
    goto :Fail
)

echo.
echo [2/5] Releasing occupied ports...
call :StopPort "%FRONTEND_PORT%"
if errorlevel 1 goto :Fail
call :StopPort "%BACKEND_PORT%"
if errorlevel 1 goto :Fail

echo.
echo [3/5] Installing backend dependencies...
python -m pip install -r "%ROOT%\backend\requirements.txt" -q
if errorlevel 1 (
    echo [ERROR] Failed to install backend dependencies.
    goto :Fail
)

echo.
echo [4/5] Installing frontend dependencies...
pushd "%ROOT%\frontend\web" && call npm install && popd
if errorlevel 1 (
    echo [ERROR] Failed to install frontend dependencies.
    goto :Fail
)

echo.
echo [4.5/5] Checking NSTL certificate...
if exist "%ROOT%\frontend\web\certs\www.nstl.gov.cn.pfx" (
    echo       NSTL certificate is ready.
) else (
    echo       Certificate not found. Trying to generate it. Administrator permission may be required.
    pushd "%ROOT%\frontend\web" && call npm run setup:nstl-local && popd
    if errorlevel 1 (
        echo [WARNING] Certificate generation failed. HTTPS may not work.
    )
)

echo.
echo [5/5] Starting services...
echo       Starting backend API: %BACKEND_URL%
start "Backend-%BACKEND_PORT%" cmd /c "cd /d ""%ROOT%\backend"" && python -m uvicorn app.main:app --host 0.0.0.0 --port %BACKEND_PORT%"
call :WaitForPort "%BACKEND_PORT%" 30
if errorlevel 1 (
    echo [ERROR] Backend API did not start on port %BACKEND_PORT%. Check the Backend-%BACKEND_PORT% window.
    goto :Fail
)

echo       Starting frontend: %FRONTEND_URL%
start "Frontend-%FRONTEND_PORT%" cmd /c "cd /d ""%ROOT%\frontend\web"" && npm run dev:nstl -- --port %FRONTEND_PORT%"
call :WaitForPort "%FRONTEND_PORT%" 30
if errorlevel 1 (
    echo [ERROR] Frontend did not start on port %FRONTEND_PORT%. Check the Frontend-%FRONTEND_PORT% window.
    goto :Fail
)

echo.
echo ============================================
echo   Startup complete
echo.
echo   Frontend: %FRONTEND_URL%
echo   API:      %BACKEND_URL%
echo   Docs:     %BACKEND_URL%/docs
echo ============================================
if /I "%NO_BROWSER%"=="1" (
    echo Browser auto-open skipped because NO_BROWSER=1.
) else (
    start "" "%FRONTEND_URL%"
)
if /I not "%NO_PAUSE%"=="1" pause
exit /b 0

:IsPortListening
netstat -ano | findstr /R /C:":%~1 .*LISTENING" >nul 2>nul
exit /b %ERRORLEVEL%

:StopPort
set "TARGET_PORT=%~1"
set "FOUND_PORT_PROCESS="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%TARGET_PORT% .*LISTENING"') do (
    if not "%%P"=="0" (
        set "FOUND_PORT_PROCESS=1"
        echo       Closing PID %%P on port %TARGET_PORT%...
        taskkill /F /PID %%P >nul 2>nul
    )
)
if not defined FOUND_PORT_PROCESS (
    echo       Port %TARGET_PORT% is free.
    exit /b 0
)
call :WaitForPortFree "%TARGET_PORT%" 15
if errorlevel 1 (
    echo [ERROR] Port %TARGET_PORT% is still occupied after closing old process.
    exit /b 1
)
echo       Port %TARGET_PORT% is free.
exit /b 0

:WaitForPortFree
set "WAIT_PORT=%~1"
set "WAIT_TRIES=%~2"
set /a WAIT_COUNT=0
:WaitForPortFreeLoop
call :IsPortListening "%WAIT_PORT%"
if errorlevel 1 exit /b 0
set /a WAIT_COUNT+=1
if !WAIT_COUNT! GEQ !WAIT_TRIES! exit /b 1
timeout /t 1 /nobreak >nul
goto :WaitForPortFreeLoop

:WaitForPort
set "WAIT_PORT=%~1"
set "WAIT_TRIES=%~2"
set /a WAIT_COUNT=0
:WaitForPortLoop
call :IsPortListening "%WAIT_PORT%"
if not errorlevel 1 exit /b 0
set /a WAIT_COUNT+=1
if !WAIT_COUNT! GEQ !WAIT_TRIES! exit /b 1
timeout /t 1 /nobreak >nul
goto :WaitForPortLoop

:Fail
echo.
echo Startup failed. Fix the error above and run start-dev.bat again.
if /I not "%NO_PAUSE%"=="1" pause
exit /b 1
