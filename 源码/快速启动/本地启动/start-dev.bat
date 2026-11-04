@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion

set "ROOT=%~dp0..\.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"
set "BACKEND_PORT=17608"
set "FRONTEND_PORT=18094"
if not defined FRONTEND_HOST set "FRONTEND_HOST=0.0.0.0"
if not defined FRONTEND_PUBLIC_HOST set "FRONTEND_PUBLIC_HOST=www.nstl.gov.cn"
if not defined FRONTEND_BASE_PATH set "FRONTEND_BASE_PATH=/ai/agent/claim_consistency/"
if not defined FRONTEND_HTTPS set "FRONTEND_HTTPS=1"
if "%FRONTEND_PORT%"=="443" (
    set "FRONTEND_URL=https://%FRONTEND_PUBLIC_HOST%%FRONTEND_BASE_PATH%"
) else (
    set "FRONTEND_URL=https://%FRONTEND_PUBLIC_HOST%:%FRONTEND_PORT%%FRONTEND_BASE_PATH%"
)
set "FRONTEND_CANONICAL_URL=https://%FRONTEND_PUBLIC_HOST%%FRONTEND_BASE_PATH%"
set "BACKEND_URL=http://127.0.0.1:%BACKEND_PORT%"

cd /d "%ROOT%"

echo ============================================
echo   Claim Consistency Agent - local dev start
echo ============================================
echo.

if not exist "backend\app\main.py" (
    echo [ERROR] backend\app\main.py not found
    pause
    exit /b 1
)
if not exist "frontend\web_demo\index.html" (
    echo [ERROR] frontend\web_demo\index.html not found
    pause
    exit /b 1
)

echo [1/2] Starting backend API on port %BACKEND_PORT%...
python -m pip install -r "%ROOT%\backend\requirements.txt" -q
python "%ROOT%\scripts\local\setup_https_cert.py" --host "%FRONTEND_PUBLIC_HOST%" --host localhost --host 127.0.0.1 --trust
if errorlevel 1 (
    echo [ERROR] Failed to prepare HTTPS certificate.
    pause
    exit /b 1
)
start "Backend-%BACKEND_PORT%" cmd /k "cd /d ""%ROOT%\backend"" && python -m uvicorn app.main:app --host 0.0.0.0 --port %BACKEND_PORT%"
echo       Waiting for backend...
timeout /t 5 /nobreak >nul

echo [2/2] Starting frontend HTTPS on port %FRONTEND_PORT%...
start "Frontend-%FRONTEND_PORT%" cmd /k "cd /d ""%ROOT%\frontend\web_demo"" && python https_server.py"

echo.
echo ============================================
echo   Startup complete. Open:
echo   %FRONTEND_URL%
echo   Canonical:
echo   %FRONTEND_CANONICAL_URL%
echo.
echo   API docs:
echo   %BACKEND_URL%/docs
echo.
echo   Ensure hosts contains: 127.0.0.1 %FRONTEND_PUBLIC_HOST%
echo ============================================
pause
