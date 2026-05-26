@echo off
cd /d "%~dp0"
echo ================================
echo   PV Video Tool V1.0
echo ================================
echo.

:: Kill existing server on port 8765
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8765.*LISTENING"') do (
    echo [Stopping old server PID %%a]
    taskkill /F /PID %%a >nul 2>&1
    timeout /t 1 /nobreak >nul
)

echo [Starting server...]
echo Server: http://127.0.0.1:8765
echo Ctrl+C to stop
echo ================================
echo.
python server.py
pause
