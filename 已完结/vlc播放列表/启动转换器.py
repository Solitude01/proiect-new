#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VLC播放列表转换器 - 快速启动脚本
"""

import os
import sys
import subprocess


def check_dependencies():
    """检查依赖是否安装"""
    try:
        import pandas
        import openpyxl
        return True
    except ImportError:
        return False


def install_dependencies():
    """安装依赖"""
    print("📦 正在安装依赖包...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✅ 依赖安装完成!")
        return True
    except subprocess.CalledProcessError:
        print("❌ 依赖安装失败，请手动运行: pip install -r requirements.txt")
        return False


def main():
    print("🎬 VLC播放列表转换器")
    print("=" * 40)

    # 检查依赖
    if not check_dependencies():
        print("⚠️  检测到缺少依赖包")
        choice = input("是否自动安装依赖? (y/n): ").lower().strip()
        if choice in ['y', 'yes', '是']:
            if not install_dependencies():
                return
        else:
            print("请手动运行: pip install -r requirements.txt")
            return

    # 启动主程序
    print("🚀 启动VLC播放列表转换器...")
    try:
        os.system("python vlc播放列表转换器_GUI.py")
    except KeyboardInterrupt:
        print("\n👋 程序已退出")


if __name__ == "__main__":
    main()