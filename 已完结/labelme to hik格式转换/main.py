#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Labelme标注转换工具 v2.0
支持单检测模式和混合标注模式的转换

作者: AI Assistant
版本: 2.0
日期: 2025-09-23
"""

import sys
import os
import tkinter as tk
from tkinter import messagebox

# 添加当前目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

try:
    from gui_components import ConverterGUI
    from converter_core import LabelmeConverter, ConversionMode
except ImportError as e:
    print(f"导入模块失败: {e}")
    print("请确保所有必要的文件都在同一目录下：")
    print("- main.py")
    print("- converter_core.py") 
    print("- gui_components.py")
    sys.exit(1)

def main():
    """主函数"""
    try:
        # 创建并运行GUI应用
        app = ConverterGUI()
        app.run()
    except Exception as e:
        # 如果GUI创建失败，显示错误信息
        root = tk.Tk()
        root.withdraw()  # 隐藏主窗口
        messagebox.showerror("启动错误", f"程序启动失败: {str(e)}")
        root.destroy()
        sys.exit(1)

if __name__ == "__main__":
    main() 