@echo off
chcp 65001 >nul
echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║           LA IIoT Multi-Instance Middleware                  ║
echo ╠══════════════════════════════════════════════════════════════╣
echo ║  Installing dependencies...                                  ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Failed to install dependencies. Please check your Python installation.
    pause
    exit /b 1
)

echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║  Configuring Windows Firewall...                             ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

:: Check for admin privileges
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] Administrator privileges required for firewall configuration.
    echo [WARNING] Please run this script as Administrator to allow external connections.
    echo.
    goto :start_server
)

:: Add firewall rule for Python/FastAPI
echo Adding firewall rule for port 8000...
netsh advfirewall firewall delete rule name="LA Middleware" >nul 2>&1
netsh advfirewall firewall add rule name="LA Middleware" dir=in action=allow protocol=tcp localport=8000

if %errorlevel% equ 0 (
    echo [OK] Firewall rule added successfully.
) else (
    echo [WARNING] Failed to add firewall rule.
)

:start_server
echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║  Starting server...                                          ║
echo ╠══════════════════════════════════════════════════════════════╣
echo ║  Server: http://localhost:8000                               ║
echo ║  API Docs: http://localhost:8000/docs                        ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.
echo Press Ctrl+C to stop the server
echo.

python main.py

pause
