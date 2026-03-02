@echo off
chcp 65001 >nul 2>&1
setlocal
cd /d "%~dp0"
set "VENV_DIR=build_venv"
set "DIST_DIR=dist"

echo ========================================
echo   NVR Download Manager - Build
echo ========================================
echo.

if exist "%VENV_DIR%" (
    echo [1/5] Cleaning old build venv...
    rmdir /s /q "%VENV_DIR%"
)

echo [2/5] Creating clean venv...
python -m venv "%VENV_DIR%"
if errorlevel 1 (
    echo ERROR: Failed to create venv
    pause
    exit /b 1
)

echo [3/5] Installing dependencies...
call "%VENV_DIR%\Scripts\activate.bat"
set "http_proxy="
set "https_proxy="
set "HTTP_PROXY="
set "HTTPS_PROXY="
pip install --quiet flask requests waitress pyinstaller
if errorlevel 1 (
    echo ERROR: pip install failed
    pause
    exit /b 1
)

echo [4/5] PyInstaller packaging...
pyinstaller --noconfirm --onefile --console ^
    --name "NVR-Manager" ^
    --add-data "download_event.py;." ^
    --distpath "%DIST_DIR%" ^
    --workpath "build_temp" ^
    --specpath "." ^
    --hidden-import waitress ^
    --hidden-import requests ^
    --hidden-import requests.auth ^
    --hidden-import urllib3 ^
    --hidden-import xml.etree ^
    --hidden-import xml.etree.ElementTree ^
    app.py
if errorlevel 1 (
    echo ERROR: PyInstaller failed
    pause
    exit /b 1
)

echo [5/5] Copying config files...
copy Deepmind.json "%DIST_DIR%\Deepmind.json" >nul 2>&1

echo.
echo Cleaning temp files...
rmdir /s /q "%VENV_DIR%" 2>nul
rmdir /s /q "build_temp" 2>nul
del /q NVR-Manager.spec 2>nul

echo.
echo ========================================
echo   Build OK!
echo   Output: %DIST_DIR%
echo.
echo     NVR-Manager.exe   (main program)
echo     Deepmind.json     (device config)
echo.
echo   Usage:
echo     NVR-Manager.exe --port 9800
echo ========================================
pause
