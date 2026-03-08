@echo off
chcp 65001 >nul
echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║           LA IIoT Multi-Instance Middleware                  ║
echo ╠══════════════════════════════════════════════════════════════╣
echo ║  Starting services...                                        ║
echo ║                                                                ║
echo ║  - Console Service:  http://localhost:8000                   ║
echo ║  - Business Service: http://localhost:6010                   ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.
echo [INFO] Starting both services in single process...
echo [INFO] Press Ctrl+C to stop both services
echo.

python start_all.py
