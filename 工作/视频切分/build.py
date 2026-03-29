#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频帧提取工具 - 一键打包脚本
"""

import os
import subprocess
import shutil
import sys


def run(cmd, **kwargs):
    """运行命令"""
    print(f">>> {cmd}")
    result = subprocess.run(cmd, shell=True, **kwargs)
    return result.returncode


def main():
    print("=" * 50)
    print("   视频帧提取工具 - 一键打包脚本")
    print("=" * 50)
    print()

    # 检查 FFmpeg
    if not os.path.exists("ffmpeg.exe"):
        print("[错误] 未找到 ffmpeg.exe，请将其复制到当前目录")
        input("按回车键退出...")
        return 1

    if not os.path.exists("ffprobe.exe"):
        print("[错误] 未找到 ffprobe.exe，请将其复制到当前目录")
        input("按回车键退出...")
        return 1

    # 检查虚拟环境
    print("[1/5] 检查虚拟环境...")
    venv_python = os.path.join("build_venv", "Scripts", "python.exe")
    if not os.path.exists(venv_python):
        print("       创建虚拟环境...")
        run("python -m venv build_venv")
    else:
        print("       虚拟环境已存在")

    pip = os.path.join("build_venv", "Scripts", "pip.exe")
    pyinstaller = os.path.join("build_venv", "Scripts", "pyinstaller.exe")

    # 安装依赖
    print()
    print("[2/5] 安装依赖...")
    run(f'"{pip}" install pyinstaller -i https://pypi.tuna.tsinghua.edu.cn/simple')

    # 清理旧构建
    print()
    print("[3/5] 清理旧构建...")
    if os.path.exists("build"):
        shutil.rmtree("build")
    if os.path.exists("dist"):
        shutil.rmtree("dist")

    # 执行打包
    print()
    print("[4/5] 执行打包...")
    cmd = (
        f'"{pyinstaller}" '
        f'--noconfirm --onedir --windowed '
        f'--add-binary "ffmpeg.exe;." '
        f'--add-binary "ffprobe.exe;." '
        f'--name "视频帧提取工具" '
        f'1.py'
    )
    if run(cmd) != 0:
        print()
        print("[错误] 打包失败！")
        input("按回车键退出...")
        return 1

    # 清理临时文件
    print()
    print("[5/5] 清理临时文件...")
    if os.path.exists("build"):
        shutil.rmtree("build")
    if os.path.exists("视频帧提取工具.spec"):
        os.remove("视频帧提取工具.spec")

    print()
    print("=" * 50)
    print("   打包成功！")
    print("=" * 50)
    print()
    print("输出目录: dist\\视频帧提取工具\\")
    print()
    print("文件列表:")
    output_dir = os.path.join("dist", "视频帧提取工具")
    if os.path.exists(output_dir):
        for f in os.listdir(output_dir):
            print(f"  - {f}")
    print()
    input("按回车键退出...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
