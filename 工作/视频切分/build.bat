@echo off
chcp 65001 >nul
title 视频帧提取工具 - 一键打包

echo ==========================================
echo    视频帧提取工具 - 一键打包脚本
echo ==========================================
echo.

:: 检查 FFmpeg 是否存在
if not exist "ffmpeg.exe" (
    echo [错误] 未找到 ffmpeg.exe，请将其复制到当前目录
    pause
    exit /b 1
)

if not exist "ffprobe.exe" (
    echo [错误] 未找到 ffprobe.exe，请将其复制到当前目录
    pause
    exit /b 1
)

echo [1/5] 检查虚拟环境...
if not exist "build_venv" (
    echo        创建虚拟环境...
    python -m venv build_venv
) else (
    echo        虚拟环境已存在
)

echo.
echo [2/5] 安装依赖...
build_venv\Scripts\pip install pyinstaller ttkbootstrap opencv-python -i https://pypi.tuna.tsinghua.edu.cn/simple -q

echo.
echo [3/5] 清理旧构建...
if exist "build" rmdir /s /q build
if exist "dist" rmdir /s /q dist

echo.
echo [4/5] 执行打包...
build_venv\Scripts\pyinstaller ^
  --noconfirm ^
  --onedir ^
  --windowed ^
  --add-binary "ffmpeg.exe;." ^
  --add-binary "ffprobe.exe;." ^
  --name "视频帧提取工具" ^
  video_frame_extractor.py

if errorlevel 1 (
    echo.
    echo [错误] 打包失败！
    pause
    exit /b 1
)

echo.
echo [5/5] 清理临时文件...
if exist "build" rmdir /s /q build
if exist "视频帧提取工具.spec" del /f /q "视频帧提取工具.spec"

echo.
echo ==========================================
echo    打包成功！
echo ==========================================
echo.
echo 输出目录: dist\视频帧提取工具\
echo.
echo 文件列表:
dir /b "dist\视频帧提取工具\"
echo.
pause
