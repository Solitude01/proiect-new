@echo off
chcp 65001 >nul
title 同步时钟源配置工具

echo ========================================
echo   同步时钟源配置工具
echo ========================================
echo.

REM 检查管理员权限
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [警告] 未以管理员权限运行！
    echo 请右键点击本脚本，选择"以管理员身份运行"
    echo.
    pause
    exit /b 1
)

echo [信息] 已获取管理员权限
echo.

REM 优先使用打包后的 EXE，否则使用 Python 脚本
if exist "%~dp0dist\时钟源配置工具.exe" (
    echo [信息] 启动打包版 EXE...
    "%~dp0dist\时钟源配置工具.exe"
) else (
    REM 检查 Python
    python --version >nul 2>&1
    if %errorLevel% neq 0 (
        echo [错误] 未找到 Python，请安装 Python 3.x
        echo 或确保 dist\时钟源配置工具.exe 存在
        pause
        exit /b 1
    )

    REM 检查 ttkbootstrap
    python -c "import ttkbootstrap" >nul 2>&1
    if %errorLevel% neq 0 (
        echo [错误] 未找到 ttkbootstrap 库
        echo 请运行: pip install ttkbootstrap
        pause
        exit /b 1
    )

    echo [信息] 启动 Python 脚本...
    python "%~dp0sync_clock_gui.py"
)
