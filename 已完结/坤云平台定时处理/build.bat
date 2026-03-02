@echo off
chcp 65001 >nul
echo ========================================
echo 坤云平台定时清理 - GUI 打包脚本
echo 使用干净虚拟环境打包
echo ========================================

REM 设置虚拟环境目录
set VENV_DIR=.build_venv

REM 创建干净的虚拟环境
if exist "%VENV_DIR%" (
    echo 清理旧的虚拟环境...
    rmdir /s /q "%VENV_DIR%"
)

echo 创建干净的虚拟环境...
python -m venv "%VENV_DIR%"
if errorlevel 1 (
    echo 创建虚拟环境失败，请确保已安装 Python 3
    pause
    exit /b 1
)

REM 激活虚拟环境
call "%VENV_DIR%\Scripts\activate.bat"

echo 安装 PyInstaller...
pip install pyinstaller --quiet
if errorlevel 1 (
    echo 安装 PyInstaller 失败
    pause
    exit /b 1
)

echo.
echo 开始打包...
pyinstaller --noconfirm --onefile --windowed ^
    --name "坤云清理管理工具" ^
    --add-data "config.json;." ^
    --add-data "cleanup.ps1;." ^
    --add-data "install.ps1;." ^
    gui/main.py

echo.
if exist "dist\坤云清理管理工具.exe" (
    echo ========================================
    echo 打包成功！
    echo 输出文件: dist\坤云清理管理工具.exe
    echo ========================================
    echo.
    echo 部署时请将以下文件放在同一目录:
    echo   - 坤云清理管理工具.exe
    echo   - config.json
    echo   - cleanup.ps1
    echo   - install.ps1
) else (
    echo 打包失败，请检查错误信息
)

REM 退出虚拟环境
call deactivate

REM 清理虚拟环境
echo.
echo 清理虚拟环境...
rmdir /s /q "%VENV_DIR%" 2>nul

REM 清理 PyInstaller 临时文件
rmdir /s /q build 2>nul
del /q "坤云清理管理工具.spec" 2>nul

pause
