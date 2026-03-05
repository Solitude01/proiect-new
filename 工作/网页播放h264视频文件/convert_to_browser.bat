@echo off
chcp 65001 > nul
echo ==========================================
echo    H264 视频转浏览器兼容格式工具
echo ==========================================
echo.

REM 检查 ffmpeg 是否安装
where ffmpeg > nul 2> nul
if errorlevel 1 (
    echo [错误] 未找到 ffmpeg，请先安装 ffmpeg 并添加到环境变量
    echo 下载地址: https://ffmpeg.org/download.html
    pause
    exit /b 1
)

if "%~1"=="" (
    echo 使用方法:
    echo   1. 将视频文件拖拽到此批处理文件上
    echo   2. 或在命令行中执行: convert_to_browser.bat 视频文件.mp4
    echo.
    echo 支持批量转换多个文件
    pause
    exit /b 1
)

echo 开始转换... (共 %~nx0 个文件)
echo.

:loop
if "%~1"=="" goto done

set "input_file=%~1"
set "file_name=%~n1"
set "file_ext=%~x1"
set "output_file=%file_name%_browser.mp4"

echo [处理中] %~nx1
echo   输入: %input_file%
echo   输出: %output_file%

ffmpeg -i "%input_file%" -c:v copy -c:a copy -movflags +faststart "%output_file%" -y

if errorlevel 1 (
    echo   [失败] 转换出错，尝试重新编码...
    ffmpeg -i "%input_file%" -c:v libx264 -c:a aac -movflags +faststart "%output_file%" -y
    if errorlevel 1 (
        echo   [错误] 转换失败
    ) else (
        echo   [成功] 转换完成（重新编码）
    )
) else (
    echo   [成功] 转换完成
)

echo.
shift
goto loop

:done
echo ==========================================
echo 转换完成！
echo ==========================================
pause
