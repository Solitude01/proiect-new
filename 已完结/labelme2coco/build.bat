@echo off
setlocal

cd /d "%~dp0"

echo [INFO] Creating temporary virtual environment ...
python -m venv .pack_venv
if errorlevel 1 (
    echo [ERROR] Failed to create virtual environment. Make sure Python is installed and in PATH.
    pause
    exit /b 1
)

call .pack_venv\Scripts\activate.bat

echo [INFO] Installing dependencies into temporary venv ...
pip install -r requirements.txt pyinstaller send2trash
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    call .pack_venv\Scripts\deactivate.bat
    rmdir /s /q .pack_venv
    pause
    exit /b 1
)

echo [INFO] Stopping existing label2coco2.7.exe process if running ...
taskkill /IM label2coco2.7.exe /F >nul 2>&1

echo [INFO] Removing old executable if it exists ...
if exist "dist\label2coco2.7.exe" (
    del /F /Q "dist\label2coco2.7.exe"
    if exist "dist\label2coco2.7.exe" (
        echo [ERROR] dist\label2coco2.7.exe is still locked. Please close it and rerun this script.
        pause
        exit /b 1
    )
)

echo [INFO] Converting icon to standard multi-resolution ICO ...
python -c "from PIL import Image; src = Image.open('ICO/COCO.ico'); src = src.convert('RGBA') if src.mode != 'RGBA' else src; sizes = [16, 24, 32, 48, 64, 128, 256]; images = [src.resize((s, s), Image.Resampling.LANCZOS) for s in sizes]; images[0].save('ICO/COCO.ico', format='ICO', bitmap_format='png', sizes=[(s, s) for s in sizes])"
if errorlevel 1 (
    echo [WARNING] Failed to convert icon, continuing with original icon ...
)

echo [INFO] Building executable with PyInstaller ...
pyinstaller --onefile --windowed --icon="ICO\COCO.ico" --add-data "ICO\COCO.ico;ICO" --name "label2coco2.7" --clean label2coco2.7.py
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed.
    call .pack_venv\Scripts\deactivate.bat
    rmdir /s /q .pack_venv
    pause
    exit /b 1
)

call .pack_venv\Scripts\deactivate.bat

echo [INFO] Cleaning up temporary virtual environment and build directory ...
rmdir /s /q .pack_venv
rmdir /s /q build

echo.
echo [SUCCESS] Build complete. Executable is located at:
echo    dist\label2coco2.7.exe
pause
