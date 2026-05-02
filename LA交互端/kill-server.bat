@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

:: Check if running as admin, if not, re-launch with elevation
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrator privileges...
    powershell -Command "Start-Process '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
    exit /b
)

echo Killing processes on ports 8000-8009 and 6010...
echo.

set PORTS=8000 8001 8002 8003 8004 8005 8006 8007 8008 8009 6010

for %%p in (%PORTS%) do (
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr :%%p ^| findstr LISTENING 2^>nul') do (
        echo   Port %%p - PID: %%a
        taskkill /F /PID %%a 2>nul
        if !errorlevel! equ 0 (
            echo   [OK] Killed PID %%a on port %%p
        ) else (
            echo   [FAIL] Could not kill PID %%a on port %%p
        )
        echo.
    )
)

echo Done.
pause
