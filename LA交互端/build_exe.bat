@echo off
chcp 65001 >nul
title LA交互端 - 打包为独立 EXE
echo ==========================================
echo    LA交互端 - 独立运行版打包工具
echo ==========================================
echo.

echo [1/5] 清理旧构建...
if exist "build" rd /s /q "build"
if exist "dist" rd /s /q "dist"
if exist "*.spec" del /f /q "*.spec"
echo [OK] 清理完成
echo.

echo [2/5] 安装/更新依赖...
pip install -r requirements.txt -q
echo [OK] 依赖已就绪
echo.

echo [3/5] 分析入口文件...
echo 主程序: main.py
echo.

echo [4/5] 开始打包（这可能需要几分钟）...
echo.

:: 打包主服务（端口8000）- 使用纯英文文件名避免编码问题
echo 打包管理控制台服务...
pyinstaller ^
    --name "LAdmin" ^
    --onefile ^
    --console ^
    --bootloader-ignore-signals ^
    --clean ^
    --add-data "templates;templates" ^
    --add-data "static;static" ^
    --add-data "configs;configs" ^
    --hidden-import uvicorn ^
    --hidden-import uvicorn.logging ^
    --hidden-import uvicorn.loops ^
    --hidden-import uvicorn.loops.auto ^
    --hidden-import uvicorn.protocols ^
    --hidden-import uvicorn.protocols.http ^
    --hidden-import uvicorn.protocols.http.auto ^
    --hidden-import uvicorn.protocols.websockets ^
    --hidden-import uvicorn.protocols.websockets.auto ^
    --hidden-import uvicorn.lifespan ^
    --hidden-import uvicorn.lifespan.on ^
    --hidden-import jinja2 ^
    --hidden-import aiofiles ^
    --hidden-import httpx ^
    --hidden-import python_multipart ^
    --hidden-import fastapi ^
    --hidden-import starlette ^
    --hidden-import pydantic ^
    --hidden-import websockets ^
    --hidden-import websockets.legacy ^
    --hidden-import websockets.legacy.server ^
    --hidden-import config_manager ^
    --hidden-import websocket_manager ^
    --collect-all fastapi ^
    --collect-all starlette ^
    --icon NONE ^
    main.py

if errorlevel 1 (
    echo [错误] 主服务打包失败！
    pause
    exit /b 1
)

:: 打包业务视图服务（端口6010）- 使用纯英文文件名
echo 打包业务视图服务...
pyinstaller ^
    --name "LView" ^
    --onefile ^
    --console ^
    --bootloader-ignore-signals ^
    --clean ^
    --add-data "templates;templates" ^
    --add-data "static;static" ^
    --add-data "configs;configs" ^
    --hidden-import uvicorn ^
    --hidden-import uvicorn.logging ^
    --hidden-import uvicorn.loops ^
    --hidden-import uvicorn.loops.auto ^
    --hidden-import uvicorn.protocols ^
    --hidden-import uvicorn.protocols.http ^
    --hidden-import uvicorn.protocols.http.auto ^
    --hidden-import uvicorn.protocols.websockets ^
    --hidden-import uvicorn.protocols.websockets.auto ^
    --hidden-import uvicorn.lifespan ^
    --hidden-import uvicorn.lifespan.on ^
    --hidden-import jinja2 ^
    --hidden-import aiofiles ^
    --hidden-import httpx ^
    --hidden-import python_multipart ^
    --hidden-import fastapi ^
    --hidden-import starlette ^
    --hidden-import pydantic ^
    --hidden-import websockets ^
    --hidden-import websockets.legacy ^
    --hidden-import websockets.legacy.server ^
    --hidden-import config_manager ^
    --hidden-import websocket_manager ^
    --collect-all fastapi ^
    --collect-all starlette ^
    --icon NONE ^
    main.py

if errorlevel 1 (
    echo [错误] 业务视图服务打包失败！
    pause
    exit /b 1
)

echo [OK] 服务打包完成
echo.

echo [5/5] 复制必要文件到输出目录...
if not exist "dist\LA交互端独立版" mkdir "dist\LA交互端独立版"
copy "dist\LAdmin.exe" "dist\LA交互端独立版\" >nul
copy "dist\LView.exe" "dist\LA交互端独立版\" >nul

:: 创建必要的空目录结构
if not exist "dist\LA交互端独立版\logs" mkdir "dist\LA交互端独立版\logs"
if not exist "dist\LA交互端独立版\configs\instances" mkdir "dist\LA交互端独立版\configs\instances"
if not exist "dist\LA交互端独立版\static\audio" mkdir "dist\LA交互端独立版\static\audio"

:: 复制静态资源（确保完整性）
xcopy /E /I /Y "templates" "dist\LA交互端独立版\templates\" >nul 2>&1
xcopy /E /I /Y "static" "dist\LA交互端独立版\static\" >nul 2>&1

:: 复制智能启动脚本（使用固定端口版本）
copy "launcher_fixed.bat" "dist\LA交互端独立版\start.bat" >nul
echo [OK] 智能启动脚本已复制

:: 复制使用说明
copy "使用说明_独立版.md" "dist\LA交互端独立版\使用说明.txt" >nul
echo [OK] 使用说明已复制

echo [OK] 文件复制完成
echo.

echo ==========================================
echo    打包成功！
echo ==========================================
echo.
echo 输出目录: dist\LA交互端独立版\
echo.
echo 包含文件:
dir /b "dist\LA交互端独立版\"
echo.
echo 部署步骤:
echo   1. 将整个 "LA交互端独立版" 文件夹复制到目标电脑
echo   2. 双击 "启动.bat" 即可运行
echo   3. 无需安装 Python！
echo.
pause
